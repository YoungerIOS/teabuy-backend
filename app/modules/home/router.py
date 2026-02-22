import json
from copy import deepcopy

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
SUPABASE_NEW_TEA_BASE = "https://nfzznasyztaontqmuhjq.supabase.co/storage/v1/object/public/product-images/home"
SUPABASE_PROMO_BASE = "https://nfzznasyztaontqmuhjq.supabase.co/storage/v1/object/public/product-images/home"


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


def default_review_payload() -> dict:
    return {"topics": default_review_topics(), "updatedAt": 0}


def default_new_tea_items() -> list[dict]:
    return [
        {
            "title": "五种健康茶",
            "subtitle": "炉火很旺，钟声很响，手中清茶正温",
            "imageUrl": f"{SUPABASE_NEW_TEA_BASE}/home_new_tea_1.png",
            "wantsText": "114人想试",
            "sort": 1,
        },
        {
            "title": "银针绿茶",
            "subtitle": "炉火很旺，钟声很响，手中清茶正温",
            "imageUrl": f"{SUPABASE_NEW_TEA_BASE}/home_new_tea_2.png",
            "wantsText": "514人想试",
            "sort": 2,
        },
        {
            "title": "碧螺春",
            "subtitle": "晨雾初起，芽叶鲜活，香气更清雅",
            "imageUrl": f"{SUPABASE_NEW_TEA_BASE}/home_new_tea_1.png",
            "wantsText": "208人想试",
            "sort": 3,
        },
        {
            "title": "花香乌龙",
            "subtitle": "花香甘润，回味绵长，适合慢品",
            "imageUrl": f"{SUPABASE_NEW_TEA_BASE}/home_new_tea_2.png",
            "wantsText": "163人想试",
            "sort": 4,
        },
    ]


def default_new_tea_payload() -> dict:
    return {
        "notice": "限量好茶免费品，品出慢时光",
        "items": default_new_tea_items(),
        "updatedAt": 0,
    }


def default_promo_sections() -> list[dict]:
    return [
        {
            "key": "flash_sale",
            "title": "今日秒杀",
            "subtitle": "2023新品客家特供碧螺春",
            "imageUrl": f"{SUPABASE_PROMO_BASE}/home_promo_flash_main_3x.png",
            "badgeText": "98%好评",
            "priceLabel": "今日价",
            "priceText": "￥200",
            "ctaText": "立即购买",
            "sort": 1,
        },
        {
            "key": "tasting_zone",
            "title": "品鉴专区",
            "subtitle": "花小钱买单泡，对胃口再下手",
            "leftImageUrl": f"{SUPABASE_PROMO_BASE}/home_promo_tasting_thumb_1_3x.png",
            "rightImageUrl": f"{SUPABASE_PROMO_BASE}/home_promo_tasting_thumb_2_3x.png",
            "sort": 2,
        },
        {
            "key": "tea_set",
            "title": "习茶套装",
            "subtitle": "花小钱买单泡，对胃口再下手",
            "leftImageUrl": f"{SUPABASE_PROMO_BASE}/home_promo_set_thumb_1_3x.png",
            "rightImageUrl": f"{SUPABASE_PROMO_BASE}/home_promo_set_thumb_2_3x.png",
            "sort": 3,
        },
    ]


def default_promo_payload() -> dict:
    return {"sections": default_promo_sections(), "updatedAt": 0}


def safe_payload(module: HomeModule) -> dict:
    raw = module.payload_json or "{}"
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}


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
                    {"key": "review", "title": "茶评", "payload": default_review_payload()},
                    {"key": "new_tea", "title": "新茶上市", "payload": default_new_tea_payload()},
                    {"key": "promo", "title": "今日秒杀", "payload": default_promo_payload()},
                ],
                "banners": default_banners(),
                "unreadCount": unread,
            }
        )

    banners = default_banners()
    review_title = "茶评"
    review_topics = default_review_topics()
    review_updated_at = 0
    for module in modules:
        if module.module_key != "banner":
            if module.module_key != "review":
                continue
            payload = json.loads(module.payload_json or "{}")
            payload_topics = payload.get("topics")
            payload_updated_at = payload.get("updatedAt")
            if isinstance(payload_topics, list) and len(payload_topics) > 0:
                review_topics = payload_topics
            if isinstance(payload_updated_at, int):
                review_updated_at = payload_updated_at
            if module.title:
                review_title = module.title
            continue

        payload = json.loads(module.payload_json or "{}")
        payload_banners = payload.get("banners")
        if isinstance(payload_banners, list) and len(payload_banners) > 0:
            banners = payload_banners

    module_items = []
    for m in modules:
        module_items.append({"key": m.module_key, "title": m.title, "payload": safe_payload(m)})

    has_review_module = any(m.get("key") == "review" for m in module_items)
    if not has_review_module:
        module_items.append(
            {"key": "review", "title": review_title, "payload": {"topics": review_topics, "updatedAt": review_updated_at}}
        )

    has_new_tea_module = any(m.get("key") == "new_tea" for m in module_items)
    if not has_new_tea_module:
        module_items.append({"key": "new_tea", "title": "新茶上市", "payload": default_new_tea_payload()})

    has_promo_module = any(m.get("key") == "promo" for m in module_items)
    if not has_promo_module:
        module_items.append({"key": "promo", "title": "今日秒杀", "payload": default_promo_payload()})

    # Keep deterministic module order for client rendering.
    module_rank = {"banner": 1, "categories": 2, "review": 3, "new_tea": 4, "promo": 5}
    module_items.sort(key=lambda item: module_rank.get(item.get("key"), 100))

    return ok(
        {
            "modules": module_items,
            "banners": deepcopy(banners),
            "unreadCount": unread,
        }
    )
