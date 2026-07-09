"""CSV export helpers."""
from __future__ import annotations

import csv
import io

from ..models import Booking
from ..timeutils import iso_utc

HEADER = ["id", "reference_code", "room_id", "user_id", "start_time", "end_time", "status", "price_cents"]


def bookings_to_csv(bookings: list[Booking]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(HEADER)
    for b in bookings:
        writer.writerow([b.id, b.reference_code, b.room_id, b.user_id, iso_utc(b.start_time), iso_utc(b.end_time), b.status, b.price_cents])
    return out.getvalue()
