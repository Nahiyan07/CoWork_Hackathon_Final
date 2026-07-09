"""Application configuration."""
from __future__ import annotations

import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./cowork.db")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-for-local-dev-secret-32-bytes-minimum")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 900
REFRESH_TOKEN_EXPIRE_DAYS = 7
SQLITE_TIMEOUT_SECONDS = int(os.getenv("SQLITE_TIMEOUT_SECONDS", "30"))
