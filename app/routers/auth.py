"""Auth endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import decode_token, hash_password, make_token_pair, revoke_access_token, verify_password
from ..database import get_db
from ..errors import AppError
from ..locks import registration_lock, token_lock
from ..models import Organization, TokenState, User
from ..schemas import LoginRequest, RefreshRequest, RegisterRequest
from ..serializers import serialize_user
from ..timeutils import utcnow

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    with registration_lock:
        org = db.query(Organization).filter(Organization.name == payload.org_name).first()
        if org is None:
            org = Organization(name=payload.org_name)
            db.add(org)
            db.flush()
            role = "admin"
        else:
            role = "member"

        existing = db.query(User).filter(User.org_id == org.id, User.username == payload.username).first()
        if existing is not None:
            raise AppError(409, "USERNAME_TAKEN", "Username already taken")

        user = User(org_id=org.id, username=payload.username, hashed_password=hash_password(payload.password), role=role)
        db.add(user)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise AppError(409, "USERNAME_TAKEN", "Username already taken") from exc
        db.refresh(user)
        return serialize_user(user)


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = (
        db.query(User)
        .join(Organization, User.org_id == Organization.id)
        .filter(Organization.name == payload.org_name, User.username == payload.username)
        .first()
    )
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise AppError(401, "INVALID_CREDENTIALS", "Invalid credentials")
    return make_token_pair(user)


@router.post("/refresh")
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    decoded = decode_token(payload.refresh_token)
    if decoded.get("type") != "refresh":
        raise AppError(401, "UNAUTHORIZED", "Wrong token type")
    with token_lock:
        state = db.query(TokenState).filter(TokenState.jti == decoded["jti"], TokenState.token_type == "refresh").first()
        if state is None or state.revoked or state.expires_at <= utcnow():
            raise AppError(401, "UNAUTHORIZED", "Invalid or expired token")
        user = db.query(User).filter(User.id == int(decoded["sub"]), User.org_id == int(decoded["org"])).first()
        if user is None:
            raise AppError(401, "UNAUTHORIZED", "Unknown user")
        state.revoked = True
        db.commit()
        return make_token_pair(user)


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    header = request.headers.get("Authorization")
    if not header or not header.startswith("Bearer "):
        raise AppError(401, "UNAUTHORIZED", "Missing bearer token")
    payload = decode_token(header[len("Bearer "):].strip())
    if payload.get("type") != "access":
        raise AppError(401, "UNAUTHORIZED", "Wrong token type")
    with token_lock:
        revoke_access_token(payload, db)
    return {"status": "ok"}
