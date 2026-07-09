"""Rolling-window POST /bookings rate limiter."""
from __future__ import annotations

from collections import defaultdict, deque
from time import monotonic

from ..errors import AppError
from ..locks import rate_limit_lock

WINDOW_SECONDS = 60.0
MAX_REQUESTS = 20
_requests: dict[int, deque[float]] = defaultdict(deque)


def record_and_check(user_id: int) -> None:
    now = monotonic()
    with rate_limit_lock:
        q = _requests[user_id]
        cutoff = now - WINDOW_SECONDS
        while q and q[0] <= cutoff:
            q.popleft()
        if len(q) >= MAX_REQUESTS:
            q.append(now)  # all requests count, including over-limit failures
            raise AppError(429, "RATE_LIMITED", "Rate limit exceeded")
        q.append(now)


def reset() -> None:
    with rate_limit_lock:
        _requests.clear()
