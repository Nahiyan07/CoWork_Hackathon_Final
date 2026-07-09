"""Model to API response conversion."""
from __future__ import annotations

from .models import Booking, RefundLog, Room, User
from .timeutils import iso_utc


def serialize_user(user: User) -> dict:
    return {"user_id": user.id, "org_id": user.org_id, "username": user.username, "role": user.role}


def serialize_room(room: Room) -> dict:
    return {
        "id": room.id,
        "org_id": room.org_id,
        "name": room.name,
        "capacity": room.capacity,
        "hourly_rate_cents": room.hourly_rate_cents,
    }


def serialize_refund(refund: RefundLog) -> dict:
    return {
        "amount_cents": refund.amount_cents,
        "status": refund.status,
        "processed_at": iso_utc(refund.processed_at),
    }


def serialize_booking(booking: Booking) -> dict:
    return {
        "id": booking.id,
        "reference_code": booking.reference_code,
        "room_id": booking.room_id,
        "user_id": booking.user_id,
        "start_time": iso_utc(booking.start_time),
        "end_time": iso_utc(booking.end_time),
        "status": booking.status,
        "price_cents": booking.price_cents,
        "created_at": iso_utc(booking.created_at),
    }
