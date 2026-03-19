from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.response import ok
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models import User, UserCredential, UserSession

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterReq(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=64)


class LoginReq(RegisterReq):
    pass


class RefreshReq(BaseModel):
    refresh_token: str


@router.post("/register")
def register(req: RegisterReq, db: Session = Depends(get_db)):
    existed = db.execute(select(User).where(User.username == req.username)).scalar_one_or_none()
    if existed:
        raise ApiError(40001, "username already exists", 400)

    user = User(username=req.username, display_name=req.username)
    db.add(user)
    db.flush()
    db.add(UserCredential(user_id=user.id, password_hash=hash_password(req.password)))
    session = UserSession(user_id=user.id, refresh_version=1, updated_at=datetime.utcnow())
    db.add(session)
    db.commit()
    return ok(
        {
            "userId": user.id,
            "user": {"id": user.id, "username": user.username, "displayName": user.display_name, "role": user.role},
            "accessToken": create_access_token(user.id, session.refresh_version),
            "refreshToken": create_refresh_token(user.id, session.refresh_version),
        }
    )


@router.post("/login")
def login(req: LoginReq, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.username == req.username)).scalar_one_or_none()
    if not user:
        raise ApiError(40111, "invalid credentials", 401)
    cred = db.execute(select(UserCredential).where(UserCredential.user_id == user.id)).scalar_one_or_none()
    if not cred or not verify_password(req.password, cred.password_hash):
        raise ApiError(40112, "invalid credentials", 401)

    session = db.execute(select(UserSession).where(UserSession.user_id == user.id)).scalar_one_or_none()
    if not session:
        session = UserSession(user_id=user.id, refresh_version=1, updated_at=datetime.utcnow())
        db.add(session)
    session.updated_at = datetime.utcnow()
    db.commit()

    return ok(
        {
            "accessToken": create_access_token(user.id, session.refresh_version),
            "refreshToken": create_refresh_token(user.id, session.refresh_version),
            "user": {"id": user.id, "username": user.username, "displayName": user.display_name, "role": user.role},
        }
    )


@router.post("/refresh")
def refresh(req: RefreshReq, db: Session = Depends(get_db)):
    from app.core.security import decode_token

    try:
        payload = decode_token(req.refresh_token)
    except Exception as exc:
        raise ApiError(40114, f"invalid refresh token: {exc}", 401)
    if payload.get("type") != "refresh":
        raise ApiError(40113, "invalid refresh token", 401)
    user_id = payload.get("sub", "")
    session = db.execute(select(UserSession).where(UserSession.user_id == user_id)).scalar_one_or_none()
    if not session:
        raise ApiError(40115, "session not found", 401)
    token_rv = int(payload.get("rv", 0))
    if token_rv != session.refresh_version:
        raise ApiError(40116, "refresh token expired", 401)
    return ok(
        {
            "accessToken": create_access_token(user_id, session.refresh_version),
            "refreshToken": create_refresh_token(user_id, session.refresh_version),
        }
    )


@router.post("/logout")
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = db.execute(select(UserSession).where(UserSession.user_id == user.id)).scalar_one_or_none()
    if session:
        session.refresh_version += 1
        session.updated_at = datetime.utcnow()
        db.commit()
    return ok({"success": True})
