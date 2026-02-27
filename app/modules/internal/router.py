import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.response import ok
from app.models import HomeModule, Order

router = APIRouter(prefix="/internal", tags=["internal"])


class BannerConfigItem(BaseModel):
    imageUrl: str
    linkType: str = "product"
    linkValue: str = ""
    sort: int = 0


class BannerConfigPayload(BaseModel):
    title: str = "推荐"
    banners: list[BannerConfigItem]


class ReviewConfigItem(BaseModel):
    title: str
    imageUrl: str
    sort: int = 0


class ReviewConfigPayload(BaseModel):
    title: str = "茶评"
    topics: list[ReviewConfigItem]


class NewTeaConfigItem(BaseModel):
    title: str
    subtitle: str = ""
    imageUrl: str
    wantsText: str = ""
    sort: int = 0


class NewTeaConfigPayload(BaseModel):
    title: str = "新茶上市"
    notice: str = "限量好茶免费品，品出慢时光"
    items: list[NewTeaConfigItem]


class PromoConfigSection(BaseModel):
    key: str
    title: str
    subtitle: str = ""
    imageUrl: str = ""
    leftImageUrl: str = ""
    rightImageUrl: str = ""
    badgeText: str = ""
    priceLabel: str = ""
    priceText: str = ""
    ctaText: str = ""
    sort: int = 0


class PromoConfigPayload(BaseModel):
    title: str = "今日秒杀"
    sections: list[PromoConfigSection]


class FeaturedPrice(BaseModel):
    currencySymbol: str = "￥"
    amount: str = ""
    unit: str = "/盒"


class FeaturedListCard(BaseModel):
    name: str
    subtitle: str = ""
    marketingText: str = ""
    soldCountText: str = ""
    badgePrimary: str = ""
    badgeSecondary: str = ""
    price: FeaturedPrice = FeaturedPrice()
    imageUrl: str
    linkType: str = "product"
    linkValue: str = ""
    sort: int = 0


class FeaturedConfigItem(BaseModel):
    title: str
    subtitle: str = ""
    imageUrl: str
    tagText: str = ""
    priceText: str = ""
    cards: list[FeaturedListCard] = []
    linkType: str = "product"
    linkValue: str = ""
    sort: int = 0


class FeaturedConfigSection(BaseModel):
    key: str
    title: str
    subtitle: str = ""
    layout: str = "grid_2x2"
    items: list[FeaturedConfigItem]
    sort: int = 0


class FeaturedConfigTab(BaseModel):
    key: str
    title: str
    sort: int = 0


class FeaturedConfigPayload(BaseModel):
    title: str = "精选"
    tabs: list[FeaturedConfigTab] = []
    activeTab: str = "recommend"
    sections: list[FeaturedConfigSection]


def _get_banner_module(db: Session) -> HomeModule | None:
    return db.execute(
        select(HomeModule).where(HomeModule.module_key == "banner").order_by(HomeModule.sort_order.asc())
    ).scalars().first()


def _get_review_module(db: Session) -> HomeModule | None:
    return db.execute(
        select(HomeModule).where(HomeModule.module_key == "review").order_by(HomeModule.sort_order.asc())
    ).scalars().first()


def _get_new_tea_module(db: Session) -> HomeModule | None:
    return db.execute(
        select(HomeModule).where(HomeModule.module_key == "new_tea").order_by(HomeModule.sort_order.asc())
    ).scalars().first()


def _get_promo_module(db: Session) -> HomeModule | None:
    return db.execute(
        select(HomeModule).where(HomeModule.module_key == "promo").order_by(HomeModule.sort_order.asc())
    ).scalars().first()


def _get_featured_module(db: Session) -> HomeModule | None:
    return db.execute(
        select(HomeModule).where(HomeModule.module_key == "featured").order_by(HomeModule.sort_order.asc())
    ).scalars().first()


def _safe_payload(module: HomeModule | None) -> dict:
    if module is None:
        return {}
    raw = module.payload_json or "{}"
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}


@router.get("/cron/order-timeout")
def cancel_timeout_orders(db: Session = Depends(get_db)):
    from app.models import OrderItem, ProductSku
    deadline = datetime.utcnow() - timedelta(minutes=30)
    rows = db.execute(
        select(Order).where(Order.status == "PENDING_PAYMENT", Order.created_at < deadline)
    ).scalars().all()
    for o in rows:
        o.status = "CANCELED"
        # Restore stock
        order_items = db.execute(select(OrderItem).where(OrderItem.order_id == o.id)).scalars().all()
        for oi in order_items:
            sku = db.get(ProductSku, oi.sku_id)
            if sku:
                sku.stock += oi.quantity
    db.commit()
    return ok({"canceled": len(rows)})


@router.get("/home/banner-config")
def get_home_banner_config(db: Session = Depends(get_db)):
    module = _get_banner_module(db)
    if not module:
        return ok({"title": "推荐", "banners": []})

    payload = _safe_payload(module)
    banners = payload.get("banners")
    if not isinstance(banners, list):
        banners = []
    return ok({"title": module.title, "banners": banners})


@router.put("/home/banner-config")
def put_home_banner_config(body: BannerConfigPayload, db: Session = Depends(get_db)):
    module = _get_banner_module(db)
    if not module:
        module = HomeModule(
            module_key="banner",
            title=body.title,
            payload_json="{}",
            sort_order=1,
            is_enabled=True,
        )
        db.add(module)

    module.title = body.title
    module.payload_json = json.dumps(
        {"banners": [item.model_dump() for item in body.banners]},
        ensure_ascii=False,
    )
    module.is_enabled = True
    db.commit()
    return ok({"updated": True, "count": len(body.banners)})


@router.get("/home/review-config")
def get_home_review_config(db: Session = Depends(get_db)):
    module = _get_review_module(db)
    if not module:
        return ok({"title": "茶评", "topics": [], "updatedAt": 0})

    payload = _safe_payload(module)
    topics = payload.get("topics")
    if not isinstance(topics, list):
        topics = []
    updated_at = payload.get("updatedAt")
    if not isinstance(updated_at, int):
        updated_at = 0
    return ok({"title": module.title or "茶评", "topics": topics, "updatedAt": updated_at})


@router.put("/home/review-config")
def put_home_review_config(body: ReviewConfigPayload, db: Session = Depends(get_db)):
    module = _get_review_module(db)
    if not module:
        module = HomeModule(
            module_key="review",
            title=body.title,
            payload_json="{}",
            sort_order=3,
            is_enabled=True,
        )
        db.add(module)

    updated_at = int(datetime.utcnow().timestamp())
    module.title = body.title
    module.payload_json = json.dumps(
        {"topics": [item.model_dump() for item in body.topics], "updatedAt": updated_at},
        ensure_ascii=False,
    )
    module.is_enabled = True
    db.commit()
    return ok({"updated": True, "count": len(body.topics), "updatedAt": updated_at})


@router.get("/home/new-tea-config")
def get_home_new_tea_config(db: Session = Depends(get_db)):
    module = _get_new_tea_module(db)
    if not module:
        return ok({"title": "新茶上市", "notice": "限量好茶免费品，品出慢时光", "items": [], "updatedAt": 0})

    payload = _safe_payload(module)
    items = payload.get("items")
    if not isinstance(items, list):
        items = []
    notice = payload.get("notice")
    if not isinstance(notice, str):
        notice = "限量好茶免费品，品出慢时光"
    updated_at = payload.get("updatedAt")
    if not isinstance(updated_at, int):
        updated_at = 0
    return ok(
        {
            "title": module.title or "新茶上市",
            "notice": notice,
            "items": items,
            "updatedAt": updated_at,
        }
    )


@router.put("/home/new-tea-config")
def put_home_new_tea_config(body: NewTeaConfigPayload, db: Session = Depends(get_db)):
    module = _get_new_tea_module(db)
    if not module:
        module = HomeModule(
            module_key="new_tea",
            title=body.title,
            payload_json="{}",
            sort_order=4,
            is_enabled=True,
        )
        db.add(module)

    updated_at = int(datetime.utcnow().timestamp())
    module.title = body.title
    module.payload_json = json.dumps(
        {
            "notice": body.notice,
            "items": [item.model_dump() for item in body.items],
            "updatedAt": updated_at,
        },
        ensure_ascii=False,
    )
    module.is_enabled = True
    db.commit()
    return ok({"updated": True, "count": len(body.items), "updatedAt": updated_at})


@router.get("/home/promo-config")
def get_home_promo_config(db: Session = Depends(get_db)):
    module = _get_promo_module(db)
    if not module:
        return ok({"title": "今日秒杀", "sections": [], "updatedAt": 0})

    payload = _safe_payload(module)
    sections = payload.get("sections")
    if not isinstance(sections, list):
        sections = []
    updated_at = payload.get("updatedAt")
    if not isinstance(updated_at, int):
        updated_at = 0
    return ok({"title": module.title or "今日秒杀", "sections": sections, "updatedAt": updated_at})


@router.put("/home/promo-config")
def put_home_promo_config(body: PromoConfigPayload, db: Session = Depends(get_db)):
    module = _get_promo_module(db)
    if not module:
        module = HomeModule(
            module_key="promo",
            title=body.title,
            payload_json="{}",
            sort_order=5,
            is_enabled=True,
        )
        db.add(module)

    updated_at = int(datetime.utcnow().timestamp())
    module.title = body.title
    module.payload_json = json.dumps(
        {"sections": [item.model_dump() for item in body.sections], "updatedAt": updated_at},
        ensure_ascii=False,
    )
    module.is_enabled = True
    db.commit()
    return ok({"updated": True, "count": len(body.sections), "updatedAt": updated_at})


@router.get("/home/featured-config")
def get_home_featured_config(db: Session = Depends(get_db)):
    module = _get_featured_module(db)
    if not module:
        return ok({"title": "精选", "tabs": [], "activeTab": "recommend", "sections": [], "updatedAt": 0})

    payload = _safe_payload(module)
    tabs = payload.get("tabs")
    if not isinstance(tabs, list):
        tabs = []
    active_tab = payload.get("activeTab")
    if not isinstance(active_tab, str):
        active_tab = "recommend"
    sections = payload.get("sections")
    if not isinstance(sections, list):
        sections = []
    updated_at = payload.get("updatedAt")
    if not isinstance(updated_at, int):
        updated_at = 0
    return ok(
        {
            "title": module.title or "精选",
            "tabs": tabs,
            "activeTab": active_tab,
            "sections": sections,
            "updatedAt": updated_at,
        }
    )


@router.put("/home/featured-config")
def put_home_featured_config(body: FeaturedConfigPayload, db: Session = Depends(get_db)):
    module = _get_featured_module(db)
    if not module:
        module = HomeModule(
            module_key="featured",
            title=body.title,
            payload_json="{}",
            sort_order=6,
            is_enabled=True,
        )
        db.add(module)

    updated_at = int(datetime.utcnow().timestamp())
    module.title = body.title
    module.payload_json = json.dumps(
        {
            "tabs": [item.model_dump() for item in body.tabs],
            "activeTab": body.activeTab,
            "sections": [item.model_dump() for item in body.sections],
            "updatedAt": updated_at,
        },
        ensure_ascii=False,
    )
    module.is_enabled = True
    db.commit()
    return ok({"updated": True, "count": len(body.sections), "updatedAt": updated_at})
