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


def _get_banner_module(db: Session) -> HomeModule | None:
    return db.execute(
        select(HomeModule).where(HomeModule.module_key == "banner").order_by(HomeModule.sort_order.asc())
    ).scalars().first()


def _get_review_module(db: Session) -> HomeModule | None:
    return db.execute(
        select(HomeModule).where(HomeModule.module_key == "review").order_by(HomeModule.sort_order.asc())
    ).scalars().first()


@router.get("/cron/order-timeout")
def cancel_timeout_orders(db: Session = Depends(get_db)):
    deadline = datetime.utcnow() - timedelta(minutes=30)
    rows = db.execute(
        select(Order).where(Order.status == "PENDING_PAYMENT", Order.created_at < deadline)
    ).scalars().all()
    for o in rows:
        o.status = "CANCELED"
    db.commit()
    return ok({"canceled": len(rows)})


@router.get("/home/banner-config")
def get_home_banner_config(db: Session = Depends(get_db)):
    module = _get_banner_module(db)
    if not module:
        return ok({"title": "推荐", "banners": []})

    payload = json.loads(module.payload_json or "{}")
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
        return ok({"title": "茶评", "topics": []})

    payload = json.loads(module.payload_json or "{}")
    topics = payload.get("topics")
    if not isinstance(topics, list):
        topics = []
    return ok({"title": module.title or "茶评", "topics": topics})


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

    module.title = body.title
    module.payload_json = json.dumps(
        {"topics": [item.model_dump() for item in body.topics]},
        ensure_ascii=False,
    )
    module.is_enabled = True
    db.commit()
    return ok({"updated": True, "count": len(body.topics)})
