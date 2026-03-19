from pydantic import BaseModel
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.response import ok
from app.models import CartItem, Product, ProductMedia, ProductSku, User

router = APIRouter(prefix="/cart", tags=["cart"])


class AddCartReq(BaseModel):
    skuId: str
    quantity: int = 1


class UpdateCartReq(BaseModel):
    quantity: int
    selected: bool | None = None


class BatchSelectReq(BaseModel):
    itemIds: list[str]
    selected: bool


def _price_text(price_cent: int) -> str:
    return f"￥{price_cent / 100:.2f}"


def _primary_image(product_id: str, db: Session) -> str:
    media = db.execute(
        select(ProductMedia).where(ProductMedia.product_id == product_id).order_by(ProductMedia.sort_order.asc())
    ).scalars().first()
    return media.media_url if media else ""


@router.get("")
def get_cart(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(CartItem).where(CartItem.user_id == user.id)).scalars().all()
    items = []
    total_cent = 0

    sku_ids = [it.sku_id for it in rows]
    skus = db.execute(select(ProductSku).where(ProductSku.id.in_(sku_ids))).scalars().all() if sku_ids else []
    sku_map = {sku.id: sku for sku in skus}

    product_ids = {sku.product_id for sku in skus}
    products = db.execute(select(Product).where(Product.id.in_(product_ids))).scalars().all() if product_ids else []
    product_map = {product.id: product for product in products}

    media_map: dict[str, str] = {}
    if product_ids:
        medias = db.execute(
            select(ProductMedia)
            .where(ProductMedia.product_id.in_(product_ids))
            .order_by(ProductMedia.product_id.asc(), ProductMedia.sort_order.asc(), ProductMedia.id.asc())
        ).scalars().all()
        for media in medias:
            if media.product_id not in media_map:
                media_map[media.product_id] = media.media_url

    for it in rows:
        sku = sku_map.get(it.sku_id)
        product = product_map.get(sku.product_id) if sku else None
        price = sku.price_cent if sku else 0
        subtotal = price * it.quantity
        if it.selected:
            total_cent += subtotal
        items.append(
            {
                "id": it.id,
                "skuId": it.sku_id,
                "quantity": it.quantity,
                "selected": it.selected,
                "unitPriceCent": price,
                "subtotalCent": subtotal,
                "subtotalText": _price_text(subtotal),
                "priceText": _price_text(price),
                "productName": product.name if product else "",
                "subtitle": product.subtitle if product else "",
                "imageUrl": media_map.get(sku.product_id, "") if sku else "",
                "badges": [
                    b for b in [product.badge_primary if product else "", product.badge_secondary if product else ""] if b
                ],
            }
        )

    cart_product_ids = {sku.product_id for sku in skus}
    rec_stmt = select(Product).where(Product.status == "active")
    if cart_product_ids:
        rec_stmt = rec_stmt.where(Product.id.not_in(cart_product_ids))
    rec_products = db.execute(rec_stmt.order_by(Product.sold_count.desc(), Product.id.desc()).limit(6)).scalars().all()
    rec_ids = [p.id for p in rec_products]

    rec_media_map: dict[str, str] = {}
    rec_price_map: dict[str, int] = {}
    rec_default_sku_map: dict[str, str] = {}
    if rec_ids:
        rec_medias = db.execute(
            select(ProductMedia)
            .where(ProductMedia.product_id.in_(rec_ids))
            .order_by(ProductMedia.product_id.asc(), ProductMedia.sort_order.asc(), ProductMedia.id.asc())
        ).scalars().all()
        for media in rec_medias:
            if media.product_id not in rec_media_map:
                rec_media_map[media.product_id] = media.media_url

        rec_skus = db.execute(
            select(ProductSku)
            .where(ProductSku.product_id.in_(rec_ids))
            .order_by(ProductSku.product_id.asc(), ProductSku.price_cent.asc(), ProductSku.id.asc())
        ).scalars().all()
        for sku in rec_skus:
            if sku.product_id not in rec_default_sku_map:
                rec_default_sku_map[sku.product_id] = sku.id
            if sku.product_id not in rec_price_map:
                rec_price_map[sku.product_id] = sku.price_cent

        if not rec_price_map:
            rec_prices = db.execute(
                select(ProductSku.product_id, func.min(ProductSku.price_cent))
                .where(ProductSku.product_id.in_(rec_ids))
                .group_by(ProductSku.product_id)
            ).all()
            for product_id, min_price in rec_prices:
                rec_price_map[str(product_id)] = int(min_price or 0)

    recommendations = [
        {
            "id": p.id,
            "name": p.name,
            "subtitle": p.subtitle,
            "imageUrl": rec_media_map.get(p.id, ""),
            "defaultSkuId": rec_default_sku_map.get(p.id, ""),
            "priceCent": rec_price_map.get(p.id, 0),
            "priceText": _price_text(rec_price_map.get(p.id, 0)),
            "marketPriceCent": p.market_price_cent,
            "badgePrimary": p.badge_primary,
            "badgeSecondary": p.badge_secondary,
        }
        for p in rec_products
    ]
    return ok({"items": items, "totalCent": total_cent, "recommendations": recommendations})


@router.post("/items")
def add_item(req: AddCartReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if req.quantity <= 0:
        raise ApiError(40004, "quantity must be > 0", 400)
    sku = db.get(ProductSku, req.skuId)
    if not sku:
        raise ApiError(40401, "sku not found", 404)
    existed = db.execute(
        select(CartItem).where(CartItem.user_id == user.id, CartItem.sku_id == req.skuId)
    ).scalar_one_or_none()
    if existed:
        existed.quantity += req.quantity
    else:
        db.add(CartItem(user_id=user.id, sku_id=req.skuId, quantity=req.quantity, selected=True))
    db.commit()
    return ok({"success": True})


@router.patch("/items/{item_id}")
def patch_item(item_id: str, req: UpdateCartReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if req.quantity <= 0:
        raise ApiError(40005, "quantity must be > 0", 400)
    item = db.get(CartItem, item_id)
    if not item or item.user_id != user.id:
        raise ApiError(40402, "cart item not found", 404)
    item.quantity = req.quantity
    if req.selected is not None:
        item.selected = req.selected
    db.commit()
    return ok({"success": True})


@router.delete("/items/{item_id}")
def delete_item(item_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(CartItem, item_id)
    if not item or item.user_id != user.id:
        raise ApiError(40403, "cart item not found", 404)
    db.delete(item)
    db.commit()
    return ok({"success": True})


@router.post("/items/select")
def batch_select(req: BatchSelectReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(CartItem).where(CartItem.user_id == user.id, CartItem.id.in_(req.itemIds))).scalars().all()
    for r in rows:
        r.selected = req.selected
    db.commit()
    return ok({"success": True})
