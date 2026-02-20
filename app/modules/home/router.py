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
SUPABASE_REVIEW_BASE = "https://nfzznasyztaontqmuhjq.supabase.co/storage/v1/object/public/product-images/home"


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


def default_review_topics() -> list[dict]:
    return [
        {"title": "红茶", "imageUrl": f"{SUPABASE_REVIEW_BASE}/home_review_bg_1.png", "sort": 1},
        {"title": "菊花茶", "imageUrl": f"{SUPABASE_REVIEW_BASE}/home_review_bg_2.png", "sort": 2},
        {"title": "绿茶", "imageUrl": f"{SUPABASE_REVIEW_BASE}/home_review_bg_3.png", "sort": 3},
        {"title": "普洱茶", "imageUrl": f"{SUPABASE_REVIEW_BASE}/home_review_bg_4.png", "sort": 4},
        {"title": "大红袍", "imageUrl": f"{SUPABASE_REVIEW_BASE}/home_review_bg_5.png", "sort": 5},
        {"title": "花茶", "imageUrl": f"{SUPABASE_REVIEW_BASE}/home_review_bg_6.png", "sort": 6},
        {"title": "白茶", "imageUrl": f"{SUPABASE_REVIEW_BASE}/home_review_bg_7.png", "sort": 7},
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
                    {"key": "review", "title": "茶评", "payload": {"topics": default_review_topics()}},
                ],
                "banners": default_banners(),
                "unreadCount": unread,
            }
        )

    banners = default_banners()
    review_title = "茶评"
    review_topics = default_review_topics()
    for module in modules:
        if module.module_key != "banner":
            if module.module_key != "review":
                continue
            payload = json.loads(module.payload_json or "{}")
            payload_topics = payload.get("topics")
            if isinstance(payload_topics, list) and len(payload_topics) > 0:
                review_topics = payload_topics
            if module.title:
                review_title = module.title
            continue

        payload = json.loads(module.payload_json or "{}")
        payload_banners = payload.get("banners")
        if isinstance(payload_banners, list) and len(payload_banners) > 0:
            banners = payload_banners

    module_items = [
        {"key": m.module_key, "title": m.title, "payload": json.loads(m.payload_json or "{}")}
        for m in modules
    ]
    has_review_module = any(m.get("key") == "review" for m in module_items)
    if not has_review_module:
        module_items.append({"key": "review", "title": review_title, "payload": {"topics": review_topics}})

    return ok(
        {
            "modules": module_items,
            "banners": banners,
            "unreadCount": unread,
        }
    )
