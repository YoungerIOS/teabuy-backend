import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.deps import get_current_user, require_admin
from app.core.errors import ApiError
from app.core.response import ok
from app.models import (
    CartItem,
    IdempotencyKey,
    Order,
    OrderItem,
    OrderPriceSnapshot,
    OrderStatusLog,
    Product,
    ProductMedia,
    ProductSku,
    User,
    UserAddress,
)
from app.services.order_status import log_order_status_change

router = APIRouter(prefix="/orders", tags=["order"])

SHIPPING_FEE_CENT = 800
FREE_SHIPPING_THRESHOLD = 10000


class PreviewReq(BaseModel):
    cartItemIds: list[str] = Field(min_length=1)


class CreateOrderReq(BaseModel):
    cartItemIds: list[str] = Field(min_length=1)
    addressId: str


def _price_text(price_cent: int) -> str:
    return f"￥{price_cent / 100:.2f}"


def _calc_preview(
    cart_items: list[CartItem],
    db: Session,
    sku_map: dict[str, ProductSku] | None = None,
    product_map: dict[str, Product] | None = None,
    media_map: dict[str, str] | None = None,
):
    if sku_map is None:
        sku_ids = [item.sku_id for item in cart_items]
        if sku_ids:
            skus = db.execute(select(ProductSku).where(ProductSku.id.in_(sku_ids))).scalars().all()
            sku_map = {sku.id: sku for sku in skus}
        else:
            sku_map = {}
    if product_map is None:
        product_ids = {sku.product_id for sku in sku_map.values()}
        if product_ids:
            products = db.execute(select(Product).where(Product.id.in_(product_ids))).scalars().all()
            product_map = {product.id: product for product in products}
        else:
            product_map = {}
    if media_map is None:
        product_ids = {sku.product_id for sku in sku_map.values()}
        media_map = {}
        if product_ids:
            medias = db.execute(
                select(ProductMedia)
                .where(ProductMedia.product_id.in_(product_ids))
                .order_by(ProductMedia.product_id.asc(), ProductMedia.sort_order.asc(), ProductMedia.id.asc())
            ).scalars().all()
            for media in medias:
                if media.product_id not in media_map:
                    media_map[media.product_id] = media.media_url
    subtotal = 0
    preview_items = []
    for item in cart_items:
        sku = sku_map.get(item.sku_id)
        if not sku:
            continue
        product = product_map.get(sku.product_id)
        line = sku.price_cent * item.quantity
        subtotal += line
        preview_items.append(
            {
                "cartItemId": item.id,
                "skuId": item.sku_id,
                "productName": product.name if product else "",
                "skuName": sku.sku_name,
                "imageUrl": media_map.get(sku.product_id, ""),
                "quantity": item.quantity,
                "priceCent": sku.price_cent,
                "subtotalCent": line,
                "subtotalText": _price_text(line),
            }
        )

    shipping = 0 if subtotal >= FREE_SHIPPING_THRESHOLD else SHIPPING_FEE_CENT
    discount = 0
    payable = subtotal + shipping - discount
    return {
        "items": preview_items,
        "subtotalCent": subtotal,
        "shippingCent": shipping,
        "discountCent": discount,
        "payableCent": payable,
    }


def _build_address_snapshot(addr: UserAddress) -> str:
    return json.dumps(
        {
            "id": addr.id,
            "recipient": addr.recipient,
            "phone": addr.phone,
            "region": addr.region,
            "detail": addr.detail,
        },
        ensure_ascii=False,
    )


def _restore_stock(order: Order, db: Session):
    order_items = db.execute(select(OrderItem).where(OrderItem.order_id == order.id)).scalars().all()
    for oi in order_items:
        sku = db.get(ProductSku, oi.sku_id)
        if sku:
            sku.stock += oi.quantity


def _action_flags(status: str) -> dict:
    return {
        "canCancel": status == "PENDING_PAYMENT",
        "canPay": status == "PENDING_PAYMENT",
        "canRefund": status in {"PAID", "SHIPPED", "COMPLETED"},
        "canConfirmDelivery": status == "SHIPPED",
    }


@router.post("/preview")
def preview(req: PreviewReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.execute(
        select(CartItem).where(CartItem.user_id == user.id, CartItem.id.in_(req.cartItemIds), CartItem.selected == True)
    ).scalars().all()
    data = _calc_preview(items, db)
    addr = db.execute(
        select(UserAddress).where(UserAddress.user_id == user.id, UserAddress.is_default == True)
    ).scalars().first()
    data["addressRequired"] = addr is None
    return ok(data)


@router.post("")
def create_order(
    req: CreateOrderReq,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not idempotency_key:
        raise ApiError(40021, "Idempotency-Key is required", 400)

    idem = db.execute(
        select(IdempotencyKey).where(IdempotencyKey.user_id == user.id, IdempotencyKey.request_key == idempotency_key)
    ).scalar_one_or_none()
    if idem:
        order = db.execute(select(Order).where(Order.order_no == idem.resource_id)).scalar_one_or_none()
        return ok(
            {
                "orderNo": idem.resource_id,
                "status": order.status if order else "PENDING_PAYMENT",
                "totalCent": order.total_cent if order else 0,
                "paymentRequired": (order.status == "PENDING_PAYMENT") if order else True,
                "idempotent": True,
            }
        )

    addr = db.get(UserAddress, req.addressId)
    if not addr or addr.user_id != user.id:
        raise ApiError(40024, "address not found", 400)

    items = db.execute(
        select(CartItem).where(CartItem.user_id == user.id, CartItem.id.in_(req.cartItemIds), CartItem.selected == True)
    ).scalars().all()
    if not items:
        raise ApiError(40022, "no selected cart items", 400)

    sku_ids = [item.sku_id for item in items]
    skus = db.execute(select(ProductSku).where(ProductSku.id.in_(sku_ids))).scalars().all()
    sku_map = {sku.id: sku for sku in skus}
    missing_skus = [item.sku_id for item in items if item.sku_id not in sku_map]
    if missing_skus:
        raise ApiError(40025, f"sku {missing_skus[0]} not found", 400)

    product_ids = {sku.product_id for sku in skus}
    products = db.execute(select(Product).where(Product.id.in_(product_ids))).scalars().all()
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

    for item in items:
        sku = sku_map.get(item.sku_id)
        if sku.stock < item.quantity:
            raise ApiError(40026, f"insufficient stock for sku {sku.sku_name}: need {item.quantity}, have {sku.stock}", 400)

    preview_data = _calc_preview(items, db, sku_map=sku_map, product_map=product_map, media_map=media_map)
    order_no = datetime.utcnow().strftime("%Y%m%d%H%M%S") + str(uuid.uuid4().int)[-6:]
    order = Order(
        order_no=order_no,
        user_id=user.id,
        address_id=addr.id,
        address_snapshot=_build_address_snapshot(addr),
        total_cent=preview_data["payableCent"],
        status="PENDING_PAYMENT",
    )
    db.add(order)
    db.flush()
    db.add(
        OrderStatusLog(
            order_id=order.id,
            from_status="",
            to_status="PENDING_PAYMENT",
            operator_id=user.id,
            operator_role=user.role,
            reason="created",
        )
    )

    for item in items:
        sku = sku_map.get(item.sku_id)
        product = product_map.get(sku.product_id) if sku else None
        db.add(
            OrderItem(
                order_id=order.id,
                sku_id=item.sku_id,
                product_name=product.name if product else "",
                sku_name=sku.sku_name if sku else "",
                image_url=media_map.get(sku.product_id, "") if sku else "",
                quantity=item.quantity,
                price_cent=sku.price_cent if sku else 0,
            )
        )
        if sku:
            sku.stock -= item.quantity

    db.add(
        OrderPriceSnapshot(
            order_id=order.id,
            subtotal_cent=preview_data["subtotalCent"],
            shipping_cent=preview_data["shippingCent"],
            discount_cent=preview_data["discountCent"],
            payable_cent=preview_data["payableCent"],
        )
    )
    db.add(IdempotencyKey(user_id=user.id, request_key=idempotency_key, resource_type="order", resource_id=order_no))

    for item in items:
        db.delete(item)
    db.commit()
    return ok(
        {
            "orderNo": order_no,
            "status": order.status,
            "totalCent": order.total_cent,
            "paymentRequired": order.status == "PENDING_PAYMENT",
            "idempotent": False,
        }
    )


@router.get("")
def list_orders(
    status: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Order).where(Order.user_id == user.id)
    if status:
        stmt = stmt.where(Order.status == status)
    rows = db.execute(stmt.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return ok(
        {
            "page": page,
            "pageSize": page_size,
            "items": [
                {
                    "orderNo": o.order_no,
                    "status": o.status,
                    "totalCent": o.total_cent,
                    "createdAt": o.created_at.isoformat(),
                    "updatedAt": o.updated_at.isoformat() if o.updated_at else o.created_at.isoformat(),
                }
                for o in rows
            ],
        }
    )


@router.get("/tab-summary")
def order_tab_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    statuses = ["PENDING_PAYMENT", "PAID", "SHIPPED", "COMPLETED"]
    alias_map = {
        "WAIT_SHIP": "PAID",
        "TO_SHIP": "PAID",
        "WAITING_SHIPMENT": "PAID",
        "DELIVERED": "COMPLETED",
    }

    def _normalize(raw_status: str | None) -> str:
        if not raw_status:
            return ""
        key = raw_status.strip().upper()
        return alias_map.get(key, key)

    rows = db.execute(
        select(Order.status, func.count()).where(Order.user_id == user.id).group_by(Order.status)
    ).all()
    counts: dict[str, int] = {}
    total = 0
    for status, count in rows:
        count_int = int(count or 0)
        total += count_int
        key = _normalize(status)
        if not key:
            continue
        counts[key] = counts.get(key, 0) + count_int

    items = [{"status": status, "count": int(counts.get(status, 0))} for status in statuses]
    return ok({"items": items, "totalCount": total})


@router.get("/{order_no}")
def order_detail(order_no: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    o = db.execute(select(Order).where(Order.order_no == order_no, Order.user_id == user.id)).scalar_one_or_none()
    if not o:
        raise ApiError(40421, "order not found", 404)
    items = db.execute(select(OrderItem).where(OrderItem.order_id == o.id)).scalars().all()
    snap = db.execute(select(OrderPriceSnapshot).where(OrderPriceSnapshot.order_id == o.id)).scalar_one_or_none()
    timeline = db.execute(select(OrderStatusLog).where(OrderStatusLog.order_id == o.id).order_by(OrderStatusLog.created_at.asc())).scalars().all()
    address = json.loads(o.address_snapshot) if o.address_snapshot else {}
    flags = _action_flags(o.status)
    return ok(
        {
            "orderNo": o.order_no,
            "status": o.status,
            "totalCent": o.total_cent,
            "address": address,
            "priceSnapshot": {
                "subtotalCent": snap.subtotal_cent if snap else 0,
                "shippingCent": snap.shipping_cent if snap else 0,
                "discountCent": snap.discount_cent if snap else 0,
                "payableCent": snap.payable_cent if snap else o.total_cent,
            },
            "statusTimeline": [
                {
                    "fromStatus": t.from_status,
                    "toStatus": t.to_status,
                    "operatorId": t.operator_id,
                    "operatorRole": t.operator_role,
                    "reason": t.reason,
                    "createdAt": t.created_at.isoformat(),
                }
                for t in timeline
            ],
            "items": [
                {
                    "skuId": i.sku_id,
                    "productName": i.product_name,
                    "skuName": i.sku_name,
                    "imageUrl": i.image_url,
                    "quantity": i.quantity,
                    "priceCent": i.price_cent,
                }
                for i in items
            ],
            **flags,
        }
    )


@router.post("/{order_no}/cancel")
def cancel_order(order_no: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    o = db.execute(select(Order).where(Order.order_no == order_no, Order.user_id == user.id)).scalar_one_or_none()
    if not o:
        raise ApiError(40422, "order not found", 404)
    if o.status != "PENDING_PAYMENT":
        raise ApiError(40023, "order cannot be cancelled", 400)
    log_order_status_change(db, o, "CANCELED", operator_id=user.id, operator_role=user.role, reason="user_cancel")
    _restore_stock(o, db)
    db.commit()
    return ok({"success": True})


@router.post("/{order_no}/ship")
def ship_order(order_no: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    o = db.execute(select(Order).where(Order.order_no == order_no)).scalar_one_or_none()
    if not o:
        raise ApiError(40423, "order not found", 404)
    if o.status != "PAID":
        raise ApiError(40027, "only paid orders can be shipped", 400)
    log_order_status_change(db, o, "SHIPPED", operator_id=admin.id, operator_role=admin.role, reason="admin_ship")
    db.commit()
    return ok({"success": True})


@router.post("/{order_no}/mock-ship")
def mock_ship_order(order_no: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if settings.payment_mode != "mock":
        raise ApiError(40031, "mock mode disabled", 400)
    o = db.execute(select(Order).where(Order.order_no == order_no, Order.user_id == user.id)).scalar_one_or_none()
    if not o:
        raise ApiError(40423, "order not found", 404)
    if o.status != "PAID":
        raise ApiError(40027, "only paid orders can be shipped", 400)
    log_order_status_change(db, o, "SHIPPED", operator_id=user.id, operator_role=user.role, reason="mock_ship")
    db.commit()
    return ok({"success": True})


@router.post("/{order_no}/confirm-delivery")
def confirm_delivery(order_no: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    o = db.execute(select(Order).where(Order.order_no == order_no, Order.user_id == user.id)).scalar_one_or_none()
    if not o:
        raise ApiError(40424, "order not found", 404)
    if o.status != "SHIPPED":
        raise ApiError(40028, "order is not in shipped status", 400)
    log_order_status_change(db, o, "COMPLETED", operator_id=user.id, operator_role=user.role, reason="user_confirm")
    db.commit()
    return ok({"success": True})
