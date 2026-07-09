"""Globally unique booking reference codes."""
from __future__ import annotations

import secrets


def next_reference_code() -> str:
    return f"CW-{secrets.token_hex(8).upper()}"
