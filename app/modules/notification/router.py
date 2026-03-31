from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.response import ok
from app.models import Notification, User

router = APIRouter(prefix="/notifications", tags=["notification"])


class MarkReadReq(BaseModel):
    read: bool = True


class ReadBatchReq(BaseModel):
    ids: list[str]


def _serialize(n: Notification) -> dict:
    return {
        "id": n.id,
        "title": n.title,
        "content": n.content,
        "isRead": n.is_read,
        "readAt": n.read_at.isoformat() if n.read_at else None,
        "createdAt": n.created_at.isoformat(),
        "updatedAt": n.updated_at.isoformat() if n.updated_at else n.created_at.isoformat(),
        "linkType": n.link_type,
        "linkValue": n.link_value,
        "type": n.type,
        "priority": n.priority,
    }


def _unread_count(user_id: str, db: Session) -> int:
    return int(
        db.execute(
            select(func.count()).select_from(Notification).where(Notification.user_id == user_id, Notification.is_read == False)
        ).scalar_one()
        or 0
    )


@router.get("/summary")
def summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    latest = db.execute(
        select(func.max(Notification.created_at)).where(Notification.user_id == user.id)
    ).scalar_one_or_none()
    return ok(
        {
            "unreadCount": _unread_count(user.id, db),
            "latestNotificationAt": latest.isoformat() if latest else None,
            "serverTime": datetime.utcnow().isoformat(),
        }
    )


@router.get("/unread-count")
def unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok({"unreadCount": _unread_count(user.id, db)})


@router.post("/read-all")
def read_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Notification).where(Notification.user_id == user.id, Notification.is_read == False)).scalars().all()
    now = datetime.utcnow()
    for n in rows:
        n.is_read = True
        n.read_at = now
        n.updated_at = now
    db.commit()
    return ok({"success": True, "unreadCount": 0})


@router.post("/read-batch")
def read_batch(req: ReadBatchReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not req.ids:
        return ok({"success": True, "unreadCount": _unread_count(user.id, db)})
    rows = db.execute(
        select(Notification).where(Notification.user_id == user.id, Notification.id.in_(req.ids))
    ).scalars().all()
    now = datetime.utcnow()
    for n in rows:
        if not n.is_read:
            n.is_read = True
            n.read_at = now
            n.updated_at = now
    db.commit()
    return ok({"success": True, "unreadCount": _unread_count(user.id, db)})


@router.patch("/{notification_id}/read")
def mark_read(
    notification_id: str,
    req: MarkReadReq | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    n = db.execute(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id)
    ).scalar_one_or_none()
    if not n:
        raise ApiError(40461, "notification not found", 404)
    read_flag = True if req is None else bool(req.read)
    now = datetime.utcnow()
    n.is_read = read_flag
    n.read_at = now if read_flag else None
    n.updated_at = now
    db.commit()
    return ok({"success": True, "unreadCount": _unread_count(user.id, db)})


@router.get("/{notification_id}")
def get_notification(notification_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.execute(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id)
    ).scalar_one_or_none()
    if not n:
        raise ApiError(40461, "notification not found", 404)
    return ok(_serialize(n))


@router.get("")
def list_notifications(
    cursor: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Notification).where(Notification.user_id == user.id)
    if cursor:
        cursor_row = db.execute(
            select(Notification).where(Notification.id == cursor, Notification.user_id == user.id)
        ).scalar_one_or_none()
        if not cursor_row:
            raise ApiError(40061, "invalid cursor", 400)
        stmt = stmt.where(
            or_(
                Notification.created_at < cursor_row.created_at,
                and_(Notification.created_at == cursor_row.created_at, Notification.id < cursor_row.id),
            )
        )
    rows = db.execute(
        stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit + 1)
    ).scalars().all()
    has_next = len(rows) > limit
    page_rows = rows[:limit]
    next_cursor = page_rows[-1].id if has_next and page_rows else ""
    return ok(
        {
            "items": [_serialize(n) for n in page_rows],
            "nextCursor": next_cursor,
            "unreadCount": _unread_count(user.id, db),
        }
    )
