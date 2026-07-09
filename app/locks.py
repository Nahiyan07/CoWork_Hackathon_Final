"""Small process-local locks for SQLite critical sections."""
from __future__ import annotations

import threading

booking_lock = threading.RLock()
registration_lock = threading.RLock()
token_lock = threading.RLock()
rate_limit_lock = threading.RLock()
