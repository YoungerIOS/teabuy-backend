from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import ApiError
from app.core.response import ok
from app.models import Product

router = APIRouter(prefix="/navigation", tags=["navigation"])


@router.get("/resolve")
def resolve_navigation(
    link_type: str = Query(alias="linkType"),
    link_value: str = Query(default="", alias="linkValue"),
    db: Session = Depends(get_db),
):
    value = link_value.strip()
    nav_type = link_type.strip().lower()

    if nav_type in {"", "none"}:
        return ok({"route": "none", "params": {}})

    if nav_type == "product":
        product = db.get(Product, value) if value else None
        if value and not product:
            raise ApiError(40461, "product not found", 404)
        return ok({"route": "product_detail", "params": {"productId": value}})

    if nav_type == "category":
        # Keep this branch DB-free to avoid click latency on home category buttons.
        return ok({"route": "product_list", "params": {"categoryKey": value}})

    if nav_type == "activity":
        return ok({"route": "product_list", "params": {"activityKey": value}})

    if nav_type == "keyword":
        return ok({"route": "product_list", "params": {"keyword": value}})

    if nav_type == "review_topic":
        return ok({"route": "review_list", "params": {"topicKey": value}})

    if nav_type == "h5":
        return ok({"route": "webview", "params": {"url": value}})

    raise ApiError(40061, "unsupported linkType", 400)
