from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.response import ok
from app.models import Notification, User

router = APIRouter(prefix="/notifications", tags=["notification"])


@router.get("/unread-count")
def unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cnt = db.query(Notification).filter(Notification.user_id == user.id, Notification.is_read == False).count()
    return ok({"unreadCount": cnt})


@router.post("/read-all")
def read_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Notification).where(Notification.user_id == user.id, Notification.is_read == False)).scalars().all()
    for n in rows:
        n.is_read = True
    db.commit()
    return ok({"success": True})
