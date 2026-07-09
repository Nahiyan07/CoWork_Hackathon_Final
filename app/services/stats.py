"""Compatibility hooks; live stats are database-derived."""
from __future__ import annotations


def record_create(*_args, **_kwargs) -> None:
    return None


def record_cancel(*_args, **_kwargs) -> None:
    return None
