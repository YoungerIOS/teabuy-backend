import json
from copy import deepcopy

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.cache import TTLCache
from app.core.db import get_db
from app.core.response import ok
from app.models import HomeModule, Notification, User
from app.core.deps import get_current_user

router = APIRouter(prefix="/home", tags=["home"])

HOME_CACHE = TTLCache(default_ttl=30, max_size=256)
HOME_CATEGORIES_TTL = 60
HOME_PAYLOAD_TTL = 30

SUPABASE_BANNER_BASE = "https://nfzznasyztaontqmuhjq.supabase.co/storage/v1/object/public/product-images/home"
SUPABASE_REVIEW_BASE = "https://nfzznasyztaontqmuhjq.supabase.co/storage/v1/object/public/product-images/home"
SUPABASE_NEW_TEA_BASE = "https://nfzznasyztaontqmuhjq.supabase.co/storage/v1/object/public/product-images/home"
SUPABASE_PROMO_BASE = "https://nfzznasyztaontqmuhjq.supabase.co/storage/v1/object/public/product-images/home"
SUPABASE_FEATURED_BASE = "https://nfzznasyztaontqmuhjq.supabase.co/storage/v1/object/public/product-images/home"


def default_category_items() -> list[dict]:
    return [
        {
            "key": "tea_bag",
            "name": "袋茶",
            "iconUrl": f"{SUPABASE_FEATURED_BASE}/home_review_bg_1.png",
            "linkType": "category",
            "linkValue": "tea_bag",
            "sort": 1,
        },
        {
            "key": "tea_pack",
            "name": "包茶",
            "iconUrl": f"{SUPABASE_FEATURED_BASE}/home_review_bg_2.png",
            "linkType": "category",
            "linkValue": "tea_pack",
            "sort": 2,
        },
        {
            "key": "teaware",
            "name": "茶具",
            "iconUrl": f"{SUPABASE_FEATURED_BASE}/home_review_bg_3.png",
            "linkType": "category",
            "linkValue": "teaware",
            "sort": 3,
        },
        {
            "key": "tea_product",
            "name": "茶制品",
            "iconUrl": f"{SUPABASE_FEATURED_BASE}/home_review_bg_4.png",
            "linkType": "category",
            "linkValue": "tea_product",
            "sort": 4,
        },
        {
            "key": "tea_region",
            "name": "茶区",
            "iconUrl": f"{SUPABASE_FEATURED_BASE}/home_review_bg_5.png",
            "linkType": "category",
            "linkValue": "tea_region",
            "sort": 5,
        },
    ]


def default_categories_payload() -> dict:
    return {"items": default_category_items(), "updatedAt": 0}


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
            "linkType": "keyword",
            "linkValue": "健康茶",
            "sort": 1,
        },
        {
            "title": "银针绿茶",
            "subtitle": "炉火很旺，钟声很响，手中清茶正温",
            "imageUrl": f"{SUPABASE_NEW_TEA_BASE}/home_new_tea_2.png",
            "wantsText": "514人想试",
            "linkType": "keyword",
            "linkValue": "银针绿茶",
            "sort": 2,
        },
        {
            "title": "碧螺春",
            "subtitle": "晨雾初起，芽叶鲜活，香气更清雅",
            "imageUrl": f"{SUPABASE_NEW_TEA_BASE}/home_new_tea_1.png",
            "wantsText": "208人想试",
            "linkType": "keyword",
            "linkValue": "碧螺春",
            "sort": 3,
        },
        {
            "title": "花香乌龙",
            "subtitle": "花香甘润，回味绵长，适合慢品",
            "imageUrl": f"{SUPABASE_NEW_TEA_BASE}/home_new_tea_2.png",
            "wantsText": "163人想试",
            "linkType": "keyword",
            "linkValue": "乌龙茶",
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
            "linkType": "product",
            "linkValue": "featured_boutique_1",
            "sort": 1,
        },
        {
            "key": "tasting_zone",
            "title": "品鉴专区",
            "subtitle": "花小钱买单泡，对胃口再下手",
            "leftImageUrl": f"{SUPABASE_PROMO_BASE}/home_promo_tasting_thumb_1_3x.png",
            "rightImageUrl": f"{SUPABASE_PROMO_BASE}/home_promo_tasting_thumb_2_3x.png",
            "linkType": "category",
            "linkValue": "cat_tea_bag",
            "sort": 2,
        },
        {
            "key": "tea_set",
            "title": "习茶套装",
            "subtitle": "花小钱买单泡，对胃口再下手",
            "leftImageUrl": f"{SUPABASE_PROMO_BASE}/home_promo_set_thumb_1_3x.png",
            "rightImageUrl": f"{SUPABASE_PROMO_BASE}/home_promo_set_thumb_2_3x.png",
            "linkType": "category",
            "linkValue": "cat_teaware",
            "sort": 3,
        },
    ]


def default_promo_payload() -> dict:
    return {"sections": default_promo_sections(), "updatedAt": 0}


def default_featured_sections() -> list[dict]:
    return [
        {
            "key": "hero_banner",
            "title": "主视觉",
            "subtitle": "",
            "layout": "banner",
            "items": [
                {
                    "title": "精选主图",
                    "subtitle": "",
                    "imageUrl": f"{SUPABASE_FEATURED_BASE}/home_banner_1.png",
                    "tagText": "",
                    "priceText": "",
                    "linkType": "activity",
                    "linkValue": "featured_hero_1",
                    "sort": 1,
                }
            ],
            "sort": 1,
        },
        {
            "key": "tea_circle",
            "title": "高山绿茶",
            "subtitle": "",
            "layout": "circle_icons",
            "items": [
                {
                    "title": "高山绿茶",
                    "subtitle": "",
                    "imageUrl": f"{SUPABASE_FEATURED_BASE}/home_review_bg_3.png",
                    "tagText": "",
                    "priceText": "",
                    "linkType": "keyword",
                    "linkValue": "高山绿茶",
                    "sort": 1,
                },
                {
                    "title": "银针绿茶",
                    "subtitle": "",
                    "imageUrl": f"{SUPABASE_FEATURED_BASE}/home_review_bg_4.png",
                    "tagText": "",
                    "priceText": "",
                    "linkType": "keyword",
                    "linkValue": "银针绿茶",
                    "sort": 2,
                },
                {
                    "title": "碧螺春",
                    "subtitle": "",
                    "imageUrl": f"{SUPABASE_FEATURED_BASE}/home_review_bg_1.png",
                    "tagText": "",
                    "priceText": "",
                    "linkType": "keyword",
                    "linkValue": "碧螺春",
                    "sort": 3,
                },
                {
                    "title": "白毛豪尖",
                    "subtitle": "",
                    "imageUrl": f"{SUPABASE_FEATURED_BASE}/home_review_bg_2.png",
                    "tagText": "",
                    "priceText": "",
                    "linkType": "keyword",
                    "linkValue": "白毛豪尖",
                    "sort": 4,
                },
                {
                    "title": "绿茶",
                    "subtitle": "",
                    "imageUrl": f"{SUPABASE_FEATURED_BASE}/home_new_tea_1.png",
                    "tagText": "",
                    "priceText": "",
                    "linkType": "keyword",
                    "linkValue": "绿茶",
                    "sort": 5,
                },
                {
                    "title": "红茶",
                    "subtitle": "",
                    "imageUrl": f"{SUPABASE_FEATURED_BASE}/home_review_bg_5.png",
                    "tagText": "",
                    "priceText": "",
                    "linkType": "keyword",
                    "linkValue": "红茶",
                    "sort": 6,
                },
                {
                    "title": "花茶",
                    "subtitle": "",
                    "imageUrl": f"{SUPABASE_FEATURED_BASE}/home_review_bg_6.png",
                    "tagText": "",
                    "priceText": "",
                    "linkType": "keyword",
                    "linkValue": "花茶",
                    "sort": 7,
                },
                {
                    "title": "白茶",
                    "subtitle": "",
                    "imageUrl": f"{SUPABASE_FEATURED_BASE}/home_review_bg_7.png",
                    "tagText": "",
                    "priceText": "",
                    "linkType": "keyword",
                    "linkValue": "白茶",
                    "sort": 8,
                },
            ],
            "sort": 2,
        },
        {
            "key": "boutique_recommend",
            "title": "精品推荐",
            "subtitle": "",
            "layout": "small_card_scroll",
            "items": [
                {
                    "title": "绿茶",
                    "subtitle": "",
                    "imageUrl": f"{SUPABASE_FEATURED_BASE}/home_new_tea_1.png",
                    "tagText": "",
                    "priceText": "￥128",
                    "linkType": "product",
                    "linkValue": "featured_boutique_1",
                    "sort": 1,
                },
                {
                    "title": "白茶",
                    "subtitle": "",
                    "imageUrl": f"{SUPABASE_FEATURED_BASE}/home_new_tea_2.png",
                    "tagText": "",
                    "priceText": "￥168",
                    "linkType": "product",
                    "linkValue": "featured_boutique_2",
                    "sort": 2,
                },
                {
                    "title": "菊花茶",
                    "subtitle": "",
                    "imageUrl": f"{SUPABASE_FEATURED_BASE}/home_review_bg_2.png",
                    "tagText": "",
                    "priceText": "￥99",
                    "linkType": "product",
                    "linkValue": "featured_boutique_3",
                    "sort": 3,
                },
                {
                    "title": "红茶",
                    "subtitle": "",
                    "imageUrl": f"{SUPABASE_FEATURED_BASE}/home_review_bg_1.png",
                    "tagText": "",
                    "priceText": "￥118",
                    "linkType": "product",
                    "linkValue": "featured_boutique_4",
                    "sort": 4,
                },
            ],
            "sort": 3,
        },
        {
            "key": "recommend_list",
            "title": "推荐",
            "subtitle": "",
            "layout": "list_card",
            "items": [
                {
                    "title": "推荐组 1",
                    "subtitle": "",
                    "imageUrl": f"{SUPABASE_FEATURED_BASE}/home_new_tea_1.png",
                    "tagText": "",
                    "priceText": "",
                    "cards": [
                        {
                            "name": "嘉应普洱茶",
                            "subtitle": "客家普洱茶",
                            "marketingText": "新品上市",
                            "soldCountText": "114214人买过",
                            "badgePrimary": "新品上市",
                            "badgeSecondary": "月销冠军",
                            "price": {"currencySymbol": "￥", "amount": "114.00", "unit": "/盒"},
                            "imageUrl": f"{SUPABASE_FEATURED_BASE}/home_new_tea_1.png",
                            "linkType": "product",
                            "linkValue": "featured_list_1_a",
                            "sort": 1,
                        },
                        {
                            "name": "嘉应菊花茶",
                            "subtitle": "嘉应丰顺茶饼",
                            "marketingText": "限时折扣",
                            "soldCountText": "114244人买过",
                            "badgePrimary": "新品上市",
                            "badgeSecondary": "限时折扣",
                            "price": {"currencySymbol": "￥", "amount": "53.00", "unit": "/盒"},
                            "imageUrl": f"{SUPABASE_FEATURED_BASE}/home_new_tea_2.png",
                            "linkType": "product",
                            "linkValue": "featured_list_1_b",
                            "sort": 2,
                        },
                    ],
                    "linkType": "activity",
                    "linkValue": "featured_list_1",
                    "sort": 1,
                },
                {
                    "title": "推荐组 2",
                    "subtitle": "",
                    "imageUrl": f"{SUPABASE_FEATURED_BASE}/home_new_tea_2.png",
                    "tagText": "",
                    "priceText": "",
                    "cards": [
                        {
                            "name": "嘉应普洱茶",
                            "subtitle": "客家普洱茶",
                            "marketingText": "新品上市",
                            "soldCountText": "114214人买过",
                            "badgePrimary": "新品上市",
                            "badgeSecondary": "月销冠军",
                            "price": {"currencySymbol": "￥", "amount": "114.00", "unit": "/盒"},
                            "imageUrl": f"{SUPABASE_FEATURED_BASE}/home_new_tea_1.png",
                            "linkType": "product",
                            "linkValue": "featured_list_2_a",
                            "sort": 1,
                        },
                        {
                            "name": "嘉应菊花茶",
                            "subtitle": "嘉应丰顺茶饼",
                            "marketingText": "限时折扣",
                            "soldCountText": "114244人买过",
                            "badgePrimary": "新品上市",
                            "badgeSecondary": "限时折扣",
                            "price": {"currencySymbol": "￥", "amount": "53.00", "unit": "/盒"},
                            "imageUrl": f"{SUPABASE_FEATURED_BASE}/home_new_tea_2.png",
                            "linkType": "product",
                            "linkValue": "featured_list_2_b",
                            "sort": 2,
                        },
                    ],
                    "linkType": "activity",
                    "linkValue": "featured_list_2",
                    "sort": 2,
                },
            ],
            "sort": 4,
        },
    ]


def default_featured_payload() -> dict:
    return {
        "tabs": [
            {"key": "recommend", "title": "推荐", "sort": 1},
            {"key": "sale", "title": "特卖", "sort": 2},
            {"key": "hot", "title": "热销", "sort": 3},
            {"key": "tea", "title": "茶叶", "sort": 4},
            {"key": "ware", "title": "茶具", "sort": 5},
        ],
        "activeTab": "hot",
        "sections": default_featured_sections(),
        "updatedAt": 0,
    }


def normalize_featured_payload(raw_payload: dict | None) -> dict:
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    defaults = default_featured_payload()

    tabs = payload.get("tabs")
    if not isinstance(tabs, list) or len(tabs) == 0:
        tabs = deepcopy(defaults["tabs"])

    active_tab = payload.get("activeTab")
    if not isinstance(active_tab, str) or active_tab.strip() == "":
        active_tab = defaults["activeTab"]

    sections = payload.get("sections")
    if not isinstance(sections, list) or len(sections) == 0:
        sections = deepcopy(defaults["sections"])
    else:
        normalized_sections: list[dict] = []
        default_by_key: dict[str, dict] = {section["key"]: section for section in defaults["sections"]}
        existing_by_key: dict[str, dict] = {}

        for section in sections:
            if not isinstance(section, dict):
                continue
            key = section.get("key")
            if not isinstance(key, str) or key.strip() == "":
                continue
            current = deepcopy(section)
            default_section = default_by_key.get(key)
            if default_section:
                if not isinstance(current.get("title"), str) or current.get("title", "").strip() == "":
                    current["title"] = default_section["title"]
                if not isinstance(current.get("layout"), str) or current.get("layout", "").strip() == "":
                    current["layout"] = default_section["layout"]
                items = current.get("items")
                if not isinstance(items, list) or len(items) == 0:
                    current["items"] = deepcopy(default_section["items"])
                if not isinstance(current.get("sort"), int):
                    current["sort"] = default_section["sort"]
            normalized_sections.append(current)
            existing_by_key[key] = current

        for default_section in defaults["sections"]:
            key = default_section["key"]
            if key not in existing_by_key:
                normalized_sections.append(deepcopy(default_section))

        sections = normalized_sections

    updated_at = payload.get("updatedAt")
    if not isinstance(updated_at, int):
        updated_at = 0

    return {
        "tabs": tabs,
        "activeTab": active_tab,
        "sections": sections,
        "updatedAt": updated_at,
    }


def safe_payload(module: HomeModule) -> dict:
    raw = module.payload_json or "{}"
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}


@router.get("/categories")
def get_home_categories(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    cache_key = ("home_categories",)
    cached = HOME_CACHE.get(cache_key)
    if cached is not None:
        return ok(cached)
    module = db.execute(
        select(HomeModule).where(HomeModule.module_key == "categories", HomeModule.is_enabled == True)
    ).scalars().first()
    if not module:
        data = {"title": "分类", **default_categories_payload()}
        HOME_CACHE.set(cache_key, data, HOME_CATEGORIES_TTL)
        return ok(data)

    payload = safe_payload(module)
    items = payload.get("items")
    if not isinstance(items, list) or len(items) == 0:
        items = default_category_items()
    updated_at = payload.get("updatedAt")
    if not isinstance(updated_at, int):
        updated_at = 0
    data = {"title": module.title or "分类", "items": items, "updatedAt": updated_at}
    HOME_CACHE.set(cache_key, data, HOME_CATEGORIES_TTL)
    return ok(data)


@router.get("")
def get_home(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cache_key = ("home_payload",)
    cached = HOME_CACHE.get(cache_key)
    unread = db.query(Notification).filter(Notification.user_id == user.id, Notification.is_read == False).count()
    if cached is not None:
        return ok({**deepcopy(cached), "unreadCount": unread})

    modules = db.execute(
        select(HomeModule).where(HomeModule.is_enabled == True).order_by(HomeModule.sort_order.asc())
    ).scalars().all()
    if not modules:
        data = {
            "modules": [
                {"key": "banner", "title": "推荐", "payload": {}},
                {"key": "categories", "title": "分类", "payload": default_categories_payload()},
                {"key": "review", "title": "茶评", "payload": default_review_payload()},
                {"key": "new_tea", "title": "新茶上市", "payload": default_new_tea_payload()},
                {"key": "promo", "title": "今日秒杀", "payload": default_promo_payload()},
                {"key": "featured", "title": "精选", "payload": default_featured_payload()},
            ],
            "banners": default_banners(),
        }
        HOME_CACHE.set(cache_key, deepcopy(data), HOME_PAYLOAD_TTL)
        return ok({**data, "unreadCount": unread})

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

    for item in module_items:
        if item.get("key") != "categories":
            continue
        payload = item.get("payload") or {}
        raw_items = payload.get("items")
        if not isinstance(raw_items, list) or len(raw_items) == 0:
            payload["items"] = default_category_items()
        if not isinstance(payload.get("updatedAt"), int):
            payload["updatedAt"] = 0
        item["payload"] = payload
        if not item.get("title"):
            item["title"] = "分类"

    for item in module_items:
        if item.get("key") != "featured":
            continue
        payload = item.get("payload") or {}
        item["payload"] = normalize_featured_payload(payload)
        if not item.get("title"):
            item["title"] = "精选"

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

    has_featured_module = any(m.get("key") == "featured" for m in module_items)
    if not has_featured_module:
        module_items.append({"key": "featured", "title": "精选", "payload": default_featured_payload()})

    has_categories_module = any(m.get("key") == "categories" for m in module_items)
    if not has_categories_module:
        module_items.append({"key": "categories", "title": "分类", "payload": default_categories_payload()})

    # Keep deterministic module order for client rendering.
    module_rank = {"banner": 1, "categories": 2, "review": 3, "new_tea": 4, "promo": 5, "featured": 6}
    module_items.sort(key=lambda item: module_rank.get(item.get("key"), 100))

    data = {"modules": module_items, "banners": deepcopy(banners)}
    HOME_CACHE.set(cache_key, deepcopy(data), HOME_PAYLOAD_TTL)
    return ok({**data, "unreadCount": unread})
