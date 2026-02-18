from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import ApiError
from app.core.security import decode_token
from app.models import User


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise ApiError(40101, "unauthorized", 401)
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_token(token)
    except Exception as exc:
        raise ApiError(40102, f"invalid token: {exc}", 401)
    user_id = payload.get("sub", "")
    user = db.get(User, user_id)
    if not user:
        raise ApiError(40103, "user not found", 401)
    return user
