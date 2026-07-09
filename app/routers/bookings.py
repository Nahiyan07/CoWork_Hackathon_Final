"""Booking creation, listing, detail and cancellation."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..database import get_db
from ..errors import AppError
from ..locks import booking_lock
from ..models import Booking, RefundLog, Room, User
from ..schemas import BookingCreateRequest
from ..serializers import serialize_booking, serialize_refund
from ..services import notifications, ratelimit, reference
from ..services.refunds import log_refund, refund_amount
from ..timeutils import parse_input_datetime, utcnow

router = APIRouter(tags=["bookings"])
MIN_DURATION_HOURS = 1
MAX_DURATION_HOURS = 8
QUOTA_LIMIT = 3
QUOTA_WINDOW_HOURS = 24


def _validate_window(start, end, now):
    if end <= start or start <= now:
        raise AppError(400, "INVALID_BOOKING_WINDOW", "Invalid booking window")
    duration_seconds = (end - start).total_seconds()
    if duration_seconds % 3600 != 0:
        raise AppError(400, "INVALID_BOOKING_WINDOW", "Invalid booking window")
    duration_hours = int(duration_seconds // 3600)
    if duration_hours < MIN_DURATION_HOURS or duration_hours > MAX_DURATION_HOURS:
        raise AppError(400, "INVALID_BOOKING_WINDOW", "Invalid booking window")
    return duration_hours


def _has_conflict(db: Session, room_id: int, start, end) -> bool:
    return (
        db.query(Booking.id)
        .filter(
            Booking.room_id == room_id,
            Booking.status == "confirmed",
            Booking.start_time < end,
            start < Booking.end_time,
        )
        .first()
        is not None
    )


def _check_quota(db: Session, user: User, now, start) -> None:
    window_end = now + timedelta(hours=QUOTA_WINDOW_HOURS)
    if not (now < start <= window_end):
        return
    count = (
        db.query(Booking.id)
        .join(Room, Booking.room_id == Room.id)
        .filter(
            Booking.user_id == user.id,
            Room.org_id == user.org_id,
            Booking.status == "confirmed",
            Booking.start_time > now,
            Booking.start_time <= window_end,
        )
        .count()
    )
    if count >= QUOTA_LIMIT:
        raise AppError(409, "QUOTA_EXCEEDED", "Booking quota exceeded")


def _booking_visible_query(db: Session, booking_id: int, user: User):
    query = (
        db.query(Booking)
        .options(joinedload(Booking.refunds))
        .join(Room, Booking.room_id == Room.id)
        .filter(Booking.id == booking_id, Room.org_id == user.org_id)
    )
    if user.role != "admin":
        query = query.filter(Booking.user_id == user.id)
    return query


@router.post("/bookings", status_code=status.HTTP_201_CREATED)
def create_booking(payload: BookingCreateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ratelimit.record_and_check(user.id)
    start = parse_input_datetime(payload.start_time)
    end = parse_input_datetime(payload.end_time)
    now = utcnow()
    duration_hours = _validate_window(start, end, now)

    with booking_lock:
        room = db.query(Room).filter(Room.id == payload.room_id, Room.org_id == user.org_id).first()
        if room is None:
            raise AppError(404, "ROOM_NOT_FOUND", "Room not found")
        if _has_conflict(db, room.id, start, end):
            raise AppError(409, "ROOM_CONFLICT", "Room already booked for this interval")
        _check_quota(db, user, now, start)

        price_cents = room.hourly_rate_cents * duration_hours
        for _ in range(5):
            booking = Booking(
                room_id=room.id,
                user_id=user.id,
                start_time=start,
                end_time=end,
                status="confirmed",
                reference_code=reference.next_reference_code(),
                price_cents=price_cents,
                created_at=now,
            )
            db.add(booking)
            try:
                db.commit()
                db.refresh(booking)
                notifications.notify_created(booking)
                return serialize_booking(booking)
            except IntegrityError:
                db.rollback()
        raise AppError(409, "ROOM_CONFLICT", "Could not create unique booking reference")


@router.get("/bookings")
def list_bookings(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    base = db.query(Booking).join(Room, Booking.room_id == Room.id).filter(Room.org_id == user.org_id)
    if user.role != "admin":
        base = base.filter(Booking.user_id == user.id)
    total = base.count()
    items = base.order_by(Booking.start_time.asc(), Booking.id.asc()).offset((page - 1) * limit).limit(limit).all()
    return {"items": [serialize_booking(b) for b in items], "page": page, "limit": limit, "total": total}


@router.get("/bookings/{booking_id}")
def get_booking(booking_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    booking = _booking_visible_query(db, booking_id, user).first()
    if booking is None:
        raise AppError(404, "BOOKING_NOT_FOUND", "Booking not found")
    response = serialize_booking(booking)
    response["refunds"] = [serialize_refund(r) for r in sorted(booking.refunds, key=lambda r: r.id)]
    return response


@router.post("/bookings/{booking_id}/cancel")
def cancel_booking(booking_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    with booking_lock:
        booking = _booking_visible_query(db, booking_id, user).first()
        if booking is None:
            raise AppError(404, "BOOKING_NOT_FOUND", "Booking not found")
        if booking.status == "cancelled":
            raise AppError(409, "ALREADY_CANCELLED", "Booking already cancelled")

        now = utcnow()
        notice = booking.start_time - now
        if notice >= timedelta(hours=48):
            refund_percent = 100
        elif notice >= timedelta(hours=24):
            refund_percent = 50
        else:
            refund_percent = 0
        refund_amount_cents = refund_amount(booking.price_cents, refund_percent)
        booking.status = "cancelled"
        existing_refund = db.query(RefundLog).filter(RefundLog.booking_id == booking.id).first()
        if existing_refund is None:
            log_refund(db, booking, refund_amount_cents)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise AppError(409, "ALREADY_CANCELLED", "Booking already cancelled")
        notifications.notify_cancelled(booking)
        return {
            "id": booking.id,
            "status": "cancelled",
            "refund_percent": refund_percent,
            "refund_amount_cents": refund_amount_cents,
        }
