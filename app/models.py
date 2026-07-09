"""SQLAlchemy ORM models for CoWork."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from .database import Base


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False, index=True)

    users = relationship("User", back_populates="organization")
    rooms = relationship("Room", back_populates="organization")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("org_id", "username", name="uq_user_org_username"),)

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    username = Column(String, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False)
    created_at = Column(DateTime, default=utcnow_naive, nullable=False)

    organization = relationship("Organization", back_populates="users")
    bookings = relationship("Booking", back_populates="user")


class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    capacity = Column(Integer, nullable=False)
    hourly_rate_cents = Column(Integer, nullable=False)

    organization = relationship("Organization", back_populates="rooms")
    bookings = relationship("Booking", back_populates="room")


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (UniqueConstraint("reference_code", name="uq_booking_reference_code"),)

    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False)
    status = Column(String, nullable=False, default="confirmed", index=True)
    reference_code = Column(String, nullable=False, index=True)
    price_cents = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=utcnow_naive, nullable=False)

    room = relationship("Room", back_populates="bookings")
    user = relationship("User", back_populates="bookings")
    refunds = relationship("RefundLog", back_populates="booking", cascade="all, delete-orphan")


class RefundLog(Base):
    __tablename__ = "refund_logs"
    __table_args__ = (UniqueConstraint("booking_id", name="uq_refund_booking_once"),)

    id = Column(Integer, primary_key=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    amount_cents = Column(Integer, nullable=False)
    status = Column(String, nullable=False)
    processed_at = Column(DateTime, default=utcnow_naive, nullable=False)

    booking = relationship("Booking", back_populates="refunds")


class TokenState(Base):
    """Refresh-token use and access-token revocation state."""

    __tablename__ = "token_states"

    jti = Column(String, primary_key=True)
    token_type = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime, default=utcnow_naive, nullable=False)
