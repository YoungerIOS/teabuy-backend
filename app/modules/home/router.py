import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.response import ok
from app.models import HomeModule, Notification, User
from app.core.deps import get_current_user

router = APIRouter(prefix="/home", tags=["home"])


@router.get("")
def get_home(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    modules = db.execute(
        select(HomeModule).where(HomeModule.is_enabled == True).order_by(HomeModule.sort_order.asc())
    ).scalars().all()
    unread = db.query(Notification).filter(Notification.user_id == user.id, Notification.is_read == False).count()
    if not modules:
        return ok(
            {
                "modules": [
                    {"key": "banner", "title": "推荐", "payload": {}},
                    {"key": "categories", "title": "分类", "payload": {}},
                ],
                "unreadCount": unread,
            }
        )
    return ok(
        {
            "modules": [
                {"key": m.module_key, "title": m.title, "payload": json.loads(m.payload_json or "{}")}
                for m in modules
            ],
            "unreadCount": unread,
        }
    )
