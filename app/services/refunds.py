"""Refund calculation/logging helpers."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from ..models import Booking, RefundLog


def refund_amount(price_cents: int, refund_percent: int) -> int:
    return int((Decimal(price_cents) * Decimal(refund_percent) / Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def log_refund(db: Session, booking: Booking, amount_cents: int) -> RefundLog:
    refund = RefundLog(booking_id=booking.id, amount_cents=amount_cents, status="processed")
    db.add(refund)
    return refund
