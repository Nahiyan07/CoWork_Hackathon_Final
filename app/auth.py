"""Password hashing, JWT issue/verify and auth dependencies."""
from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from datetime import datetime, timezone

import jwt
from fastapi import Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import (
    ACCESS_TOKEN_EXPIRE_SECONDS,
    JWT_ALGORITHM,
    JWT_SECRET,
    REFRESH_TOKEN_EXPIRE_DAYS,
)
from .database import SessionLocal, get_db
from .errors import AppError
from .locks import token_lock
from .models import TokenState, User


# This makes Swagger UI show the Authorize button.
bearer_scheme = HTTPBearer(auto_error=False)

_PBKDF2_ROUNDS = 100_000


def hash_password(password: str) -> str:
    """
    Hash a plain-text password using PBKDF2-HMAC-SHA256.
    Stored format: salt_hex:hash_hex
    """
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        salt,
        _PBKDF2_ROUNDS,
    )
    return f"{salt.hex()}:{dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """
    Verify plain password against stored PBKDF2 hash.
    """
    try:
        salt_hex, dk_hex = stored.split(":")
    except ValueError:
        return False

    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        bytes.fromhex(salt_hex),
        _PBKDF2_ROUNDS,
    )

    return hmac.compare_digest(dk.hex(), dk_hex)


def _now_ts() -> int:
    """
    Current UTC timestamp in seconds.
    """
    return int(datetime.now(timezone.utc).timestamp())


def _encode_token(user: User, token_type: str, lifetime_seconds: int) -> tuple[str, dict]:
    """
    Create JWT payload and encoded token.

    Required claims:
    sub, org, role, jti, iat, exp, type
    """
    iat = _now_ts()

    payload = {
        "sub": str(user.id),
        "org": user.org_id,
        "role": user.role,
        "jti": uuid.uuid4().hex,
        "iat": iat,
        "exp": iat + lifetime_seconds,
        "type": token_type,
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, payload


def create_access_token(user: User) -> str:
    """
    Create access token.

    Access token lifetime must be exactly 900 seconds.
    """
    token, _payload = _encode_token(
        user=user,
        token_type="access",
        lifetime_seconds=ACCESS_TOKEN_EXPIRE_SECONDS,
    )
    return token


def create_refresh_token(user: User) -> str:
    """
    Create refresh token and store its JTI.

    Refresh tokens are single-use. Their JTI is stored in TokenState.
    """
    lifetime_seconds = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600

    token, payload = _encode_token(
        user=user,
        token_type="refresh",
        lifetime_seconds=lifetime_seconds,
    )

    with token_lock:
        db = SessionLocal()
        try:
            db.add(
                TokenState(
                    jti=payload["jti"],
                    token_type="refresh",
                    user_id=user.id,
                    expires_at=datetime.fromtimestamp(
                        int(payload["exp"]),
                        timezone.utc,
                    ).replace(tzinfo=None),
                    revoked=False,
                )
            )
            db.commit()
        finally:
            db.close()

    return token


def make_token_pair(user: User) -> dict:
    """
    Return login/refresh response shape.
    """
    return {
        "access_token": create_access_token(user),
        "refresh_token": create_refresh_token(user),
        "token_type": "bearer",
    }


def decode_token(token: str) -> dict:
    """
    Decode JWT token and validate required claims.
    """
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
        )
    except jwt.PyJWTError as exc:
        raise AppError(
            401,
            "UNAUTHORIZED",
            "Invalid or expired token",
        ) from exc

    required_claims = {
        "sub",
        "org",
        "role",
        "jti",
        "iat",
        "exp",
        "type",
    }

    if not required_claims.issubset(payload):
        raise AppError(
            401,
            "UNAUTHORIZED",
            "Invalid token",
        )

    return payload


def revoke_access_token(payload: dict, db: Session) -> None:
    """
    Blacklist the presented access token during logout.
    """
    jti = payload["jti"]

    existing = db.query(TokenState).filter(
        TokenState.jti == jti,
    ).first()

    expires_at = datetime.fromtimestamp(
        int(payload["exp"]),
        timezone.utc,
    ).replace(tzinfo=None)

    if existing is None:
        db.add(
            TokenState(
                jti=jti,
                token_type="access",
                user_id=int(payload["sub"]),
                expires_at=expires_at,
                revoked=True,
            )
        )
    else:
        existing.revoked = True

    db.commit()


def _is_revoked(payload: dict, db: Session) -> bool:
    """
    Check whether token JTI is revoked/blacklisted.
    """
    row = db.query(TokenState).filter(
        TokenState.jti == payload["jti"],
        TokenState.revoked.is_(True),
    ).first()

    return row is not None


def get_token_payload(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    db: Session = Depends(get_db),
) -> dict:
    """
    FastAPI dependency for authenticated routes.

    This dependency is also what makes Swagger UI understand that endpoints
    require Bearer authentication and show the Authorize button.
    """
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not credentials.credentials
    ):
        raise AppError(
            401,
            "UNAUTHORIZED",
            "Missing bearer token",
        )

    payload = decode_token(credentials.credentials.strip())

    if payload.get("type") != "access":
        raise AppError(
            401,
            "UNAUTHORIZED",
            "Wrong token type",
        )

    if _is_revoked(payload, db):
        raise AppError(
            401,
            "UNAUTHORIZED",
            "Token has been revoked",
        )

    return payload


def get_current_user(
    payload: dict = Depends(get_token_payload),
    db: Session = Depends(get_db),
) -> User:
    """
    Return current authenticated user.
    """
    user = db.query(User).filter(
        User.id == int(payload["sub"]),
        User.org_id == int(payload["org"]),
    ).first()

    if user is None:
        raise AppError(
            401,
            "UNAUTHORIZED",
            "Unknown user",
        )

    return user


def require_admin(
    user: User = Depends(get_current_user),
) -> User:
    """
    Admin-only dependency.
    """
    if user.role != "admin":
        raise AppError(
            403,
            "FORBIDDEN",
            "Admin privileges required",
        )

    return user
