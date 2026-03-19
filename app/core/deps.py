from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import ApiError
from app.core.request_context import set_actor
from app.core.security import decode_token
from app.models import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not credentials or not credentials.credentials:
        raise ApiError(40101, "unauthorized", 401)
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except Exception as exc:
        raise ApiError(40102, f"invalid token: {exc}", 401)
    if payload.get("type") != "access":
        raise ApiError(40104, "invalid access token type", 401)
    user_id = payload.get("sub", "")
    user = db.get(User, user_id)
    if not user:
        raise ApiError(40103, "user not found", 401)
    set_actor(user.id, user.role)
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise ApiError(40301, "admin role required", 403)
    return user
