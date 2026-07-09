"""Room listing/creation and live availability/stats."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_admin
from ..database import get_db
from ..errors import AppError
from ..models import Booking, Room, User
from ..schemas import RoomCreateRequest
from ..serializers import serialize_room
from ..timeutils import day_bounds_utc, iso_utc, parse_date

router = APIRouter(tags=["rooms"])


@router.get("/rooms")
def list_rooms(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rooms = db.query(Room).filter(Room.org_id == user.org_id).order_by(Room.id.asc()).all()
    return [serialize_room(room) for room in rooms]


@router.post("/rooms", status_code=status.HTTP_201_CREATED)
def create_room(payload: RoomCreateRequest, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    room = Room(org_id=user.org_id, name=payload.name, capacity=payload.capacity, hourly_rate_cents=payload.hourly_rate_cents)
    db.add(room)
    db.commit()
    db.refresh(room)
    return serialize_room(room)


def _room_or_404(db: Session, room_id: int, org_id: int) -> Room:
    room = db.query(Room).filter(Room.id == room_id, Room.org_id == org_id).first()
    if room is None:
        raise AppError(404, "ROOM_NOT_FOUND", "Room not found")
    return room


@router.get("/rooms/{room_id}/availability")
def availability(
    room_id: int,
    date: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    room = _room_or_404(db, room_id, user.org_id)
    day = parse_date(date)
    start, end = day_bounds_utc(day)
    bookings = (
        db.query(Booking)
        .filter(Booking.room_id == room.id, Booking.status == "confirmed", Booking.start_time >= start, Booking.start_time < end)
        .order_by(Booking.start_time.asc(), Booking.id.asc())
        .all()
    )
    return {
        "room_id": room.id,
        "date": day.isoformat(),
        "busy": [{"start_time": iso_utc(b.start_time), "end_time": iso_utc(b.end_time)} for b in bookings],
    }


@router.get("/rooms/{room_id}/stats")
def room_stats(room_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    room = _room_or_404(db, room_id, user.org_id)
    row = (
        db.query(func.count(Booking.id), func.coalesce(func.sum(Booking.price_cents), 0))
        .filter(Booking.room_id == room.id, Booking.status == "confirmed")
        .one()
    )
    return {"room_id": room.id, "total_confirmed_bookings": int(row[0]), "total_revenue_cents": int(row[1] or 0)}
