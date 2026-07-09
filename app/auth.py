"""Password hashing, JWT issue/verify and auth dependencies."""
from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .config import ACCESS_TOKEN_EXPIRE_SECONDS, JWT_ALGORITHM, JWT_SECRET, REFRESH_TOKEN_EXPIRE_DAYS
from .database import SessionLocal, get_db
from .errors import AppError
from .locks import token_lock
from .models import TokenState, User
from .timeutils import utcnow

_PBKDF2_ROUNDS = 100_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return f"{salt.hex()}:{dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split(":")
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), _PBKDF2_ROUNDS)
    return hmac.compare_digest(dk.hex(), dk_hex)


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _encode_token(user: User, token_type: str, lifetime_seconds: int) -> tuple[str, dict]:
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
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM), payload


def create_access_token(user: User) -> str:
    token, _payload = _encode_token(user, "access", ACCESS_TOKEN_EXPIRE_SECONDS)
    return token


def create_refresh_token(user: User) -> str:
    lifetime_seconds = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600
    token, payload = _encode_token(user, "refresh", lifetime_seconds)
    with token_lock:
        db = SessionLocal()
        try:
            db.add(
                TokenState(
                    jti=payload["jti"],
                    token_type="refresh",
                    user_id=user.id,
                    expires_at=datetime.fromtimestamp(payload["exp"], timezone.utc).replace(tzinfo=None),
                    revoked=False,
                )
            )
            db.commit()
        finally:
            db.close()
    return token


def make_token_pair(user: User) -> dict:
    return {
        "access_token": create_access_token(user),
        "refresh_token": create_refresh_token(user),
        "token_type": "bearer",
    }


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise AppError(401, "UNAUTHORIZED", "Invalid or expired token") from exc
    required = {"sub", "org", "role", "jti", "iat", "exp", "type"}
    if not required.issubset(payload):
        raise AppError(401, "UNAUTHORIZED", "Invalid token")
    return payload


def revoke_access_token(payload: dict, db: Session) -> None:
    jti = payload["jti"]
    existing = db.query(TokenState).filter(TokenState.jti == jti).first()
    if existing is None:
        db.add(
            TokenState(
                jti=jti,
                token_type="access",
                user_id=int(payload["sub"]),
                expires_at=datetime.fromtimestamp(int(payload["exp"]), timezone.utc).replace(tzinfo=None),
                revoked=True,
            )
        )
    else:
        existing.revoked = True
    db.commit()


def _is_revoked(payload: dict, db: Session) -> bool:
    row = db.query(TokenState).filter(TokenState.jti == payload["jti"], TokenState.revoked.is_(True)).first()
    return row is not None


def get_token_payload(request: Request, db: Session = Depends(get_db)) -> dict:
    header = request.headers.get("Authorization")
    if not header or not header.startswith("Bearer "):
        raise AppError(401, "UNAUTHORIZED", "Missing bearer token")
    token = header[len("Bearer "):].strip()
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise AppError(401, "UNAUTHORIZED", "Wrong token type")
    if _is_revoked(payload, db):
        raise AppError(401, "UNAUTHORIZED", "Token has been revoked")
    return payload


def get_current_user(payload: dict = Depends(get_token_payload), db: Session = Depends(get_db)) -> User:
    user = db.query(User).filter(User.id == int(payload["sub"]), User.org_id == int(payload["org"])).first()
    if user is None:
        raise AppError(401, "UNAUTHORIZED", "Unknown user")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise AppError(403, "FORBIDDEN", "Admin privileges required")
    return user
