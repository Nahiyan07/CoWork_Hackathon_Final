"""No-op notification facade for the challenge app."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def notify_created(booking) -> None:
    logger.info("booking created: %s", getattr(booking, "reference_code", None))


def notify_cancelled(booking) -> None:
    logger.info("booking cancelled: %s", getattr(booking, "reference_code", None))
