"""Datetime parsing and UTC serialization helpers."""
from __future__ import annotations

from datetime import date, datetime, time, timezone, timedelta

from .errors import AppError


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_input_datetime(value: str) -> datetime:
    """Parse ISO 8601, convert aware input to UTC, treat naive input as UTC.

    Returns a naive UTC datetime for SQLite storage/comparison.
    """
    try:
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        parsed = datetime.fromisoformat(normalized)
    except Exception as exc:  # noqa: BLE001
        raise AppError(400, "INVALID_BOOKING_WINDOW", "Invalid datetime") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise AppError(400, "INVALID_BOOKING_WINDOW", "Invalid date") from exc


def day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min)
    return start, start + timedelta(days=1)


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    value = value.replace(microsecond=0)
    return value.isoformat().replace("+00:00", "Z")
