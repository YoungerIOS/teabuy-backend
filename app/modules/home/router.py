import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.response import ok
from app.models import HomeModule, Notification, User
from app.core.deps import get_current_user

router = APIRouter(prefix="/home", tags=["home"])

SUPABASE_BANNER_BASE = "https://nfzznasyztaontqmuhjq.supabase.co/storage/v1/object/public/product-images/home"


def default_banners() -> list[dict]:
    return [
        {
            "imageUrl": f"{SUPABASE_BANNER_BASE}/home_banner_1.png",
            "linkType": "product",
            "linkValue": "banner_1",
            "sort": 1,
        },
        {
            "imageUrl": f"{SUPABASE_BANNER_BASE}/home_banner_2.png",
            "linkType": "product",
            "linkValue": "banner_2",
            "sort": 2,
        },
        {
            "imageUrl": f"{SUPABASE_BANNER_BASE}/home_banner_3.png",
            "linkType": "product",
            "linkValue": "banner_3",
            "sort": 3,
        },
        {
            "imageUrl": f"{SUPABASE_BANNER_BASE}/home_banner_4.png",
            "linkType": "product",
            "linkValue": "banner_4",
            "sort": 4,
        },
        {
            "imageUrl": f"{SUPABASE_BANNER_BASE}/home_banner_5.png",
            "linkType": "product",
            "linkValue": "banner_5",
            "sort": 5,
        },
    ]


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
                "banners": default_banners(),
                "unreadCount": unread,
            }
        )

    banners = default_banners()
    for module in modules:
        if module.module_key != "banner":
            continue
        payload = json.loads(module.payload_json or "{}")
        payload_banners = payload.get("banners")
        if isinstance(payload_banners, list) and len(payload_banners) > 0:
            banners = payload_banners
        break

    return ok(
        {
            "modules": [
                {"key": m.module_key, "title": m.title, "payload": json.loads(m.payload_json or "{}")}
                for m in modules
            ],
            "banners": banners,
            "unreadCount": unread,
        }
    )
