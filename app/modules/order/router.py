from datetime import datetime
import uuid

from pydantic import BaseModel
from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.response import ok
from app.models import CartItem, IdempotencyKey, Order, OrderItem, OrderPriceSnapshot, ProductSku, User

router = APIRouter(prefix="/orders", tags=["order"])


class PreviewReq(BaseModel):
    cartItemIds: list[str]


class CreateOrderReq(BaseModel):
    cartItemIds: list[str]


def _calc_preview(cart_items: list[CartItem], db: Session):
    subtotal = 0
    for item in cart_items:
        sku = db.get(ProductSku, item.sku_id)
        price = sku.price_cent if sku else 0
        subtotal += price * item.quantity
    shipping = 0
    discount = 0
    payable = subtotal + shipping - discount
    return {
        "subtotalCent": subtotal,
        "shippingCent": shipping,
        "discountCent": discount,
        "payableCent": payable,
    }


@router.post("/preview")
def preview(req: PreviewReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.execute(
        select(CartItem).where(CartItem.user_id == user.id, CartItem.id.in_(req.cartItemIds), CartItem.selected == True)
    ).scalars().all()
    return ok(_calc_preview(items, db))


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
        return ok({"orderNo": idem.resource_id, "idempotent": True})

    items = db.execute(
        select(CartItem).where(CartItem.user_id == user.id, CartItem.id.in_(req.cartItemIds), CartItem.selected == True)
    ).scalars().all()
    if not items:
        raise ApiError(40022, "no selected cart items", 400)

    order_no = datetime.utcnow().strftime("%Y%m%d%H%M%S") + str(uuid.uuid4().int)[-6:]
    preview = _calc_preview(items, db)

    order = Order(order_no=order_no, user_id=user.id, total_cent=preview["payableCent"], status="PENDING_PAYMENT")
    db.add(order)
    db.flush()

    for item in items:
        sku = db.get(ProductSku, item.sku_id)
        unit_price = sku.price_cent if sku else 0
        db.add(OrderItem(order_id=order.id, sku_id=item.sku_id, quantity=item.quantity, price_cent=unit_price))

    db.add(
        OrderPriceSnapshot(
            order_id=order.id,
            subtotal_cent=preview["subtotalCent"],
            shipping_cent=preview["shippingCent"],
            discount_cent=preview["discountCent"],
            payable_cent=preview["payableCent"],
        )
    )
    db.add(
        IdempotencyKey(user_id=user.id, request_key=idempotency_key, resource_type="order", resource_id=order_no)
    )
    db.commit()
    return ok({"orderNo": order_no, "idempotent": False})


@router.get("")
def list_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc())).scalars().all()
    return ok(
        [
            {
                "orderNo": o.order_no,
                "status": o.status,
                "totalCent": o.total_cent,
                "createdAt": o.created_at.isoformat(),
            }
            for o in rows
        ]
    )


@router.get("/{order_no}")
def order_detail(order_no: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    o = db.execute(select(Order).where(Order.order_no == order_no, Order.user_id == user.id)).scalar_one_or_none()
    if not o:
        raise ApiError(40421, "order not found", 404)
    items = db.execute(select(OrderItem).where(OrderItem.order_id == o.id)).scalars().all()
    return ok(
        {
            "orderNo": o.order_no,
            "status": o.status,
            "totalCent": o.total_cent,
            "items": [{"skuId": i.sku_id, "quantity": i.quantity, "priceCent": i.price_cent} for i in items],
        }
    )


@router.post("/{order_no}/cancel")
def cancel_order(order_no: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    o = db.execute(select(Order).where(Order.order_no == order_no, Order.user_id == user.id)).scalar_one_or_none()
    if not o:
        raise ApiError(40422, "order not found", 404)
    if o.status != "PENDING_PAYMENT":
        raise ApiError(40023, "order cannot be cancelled", 400)
    o.status = "CANCELED"
    db.commit()
    return ok({"success": True})
