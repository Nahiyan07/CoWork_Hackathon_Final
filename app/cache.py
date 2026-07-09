"""Compatibility cache API.

The original challenge used stale in-memory caches for live data. These no-op helpers keep
call sites simple while forcing reports, availability and stats to read the database every time.
"""
from __future__ import annotations


def invalidate_availability(*_args, **_kwargs) -> None:
    return None


def invalidate_report(*_args, **_kwargs) -> None:
    return None


def invalidate_stats(*_args, **_kwargs) -> None:
    return None
