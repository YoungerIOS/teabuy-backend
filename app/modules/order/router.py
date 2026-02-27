import json
import uuid
from datetime import datetime

from pydantic import BaseModel
from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.response import ok
from app.models import (
    CartItem,
    IdempotencyKey,
    Order,
    OrderItem,
    OrderPriceSnapshot,
    Product,
    ProductMedia,
    ProductSku,
    User,
    UserAddress,
)

router = APIRouter(prefix="/orders", tags=["order"])

# -- Shipping rules ----------------------------------------------------------
SHIPPING_FEE_CENT = 800         # ¥8 default
FREE_SHIPPING_THRESHOLD = 10000  # ¥100 free shipping


class PreviewReq(BaseModel):
    cartItemIds: list[str]


class CreateOrderReq(BaseModel):
    cartItemIds: list[str]
    addressId: str


def _calc_preview(cart_items: list[CartItem], db: Session):
    subtotal = 0
    for item in cart_items:
        sku = db.get(ProductSku, item.sku_id)
        price = sku.price_cent if sku else 0
        subtotal += price * item.quantity
    shipping = 0 if subtotal >= FREE_SHIPPING_THRESHOLD else SHIPPING_FEE_CENT
    discount = 0
    payable = subtotal + shipping - discount
    return {
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


def _get_product_image(product_id: str, db: Session) -> str:
    media = db.execute(
        select(ProductMedia).where(ProductMedia.product_id == product_id).order_by(ProductMedia.sort_order.asc())
    ).scalars().first()
    return media.media_url if media else ""


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

    # Idempotency check
    idem = db.execute(
        select(IdempotencyKey).where(IdempotencyKey.user_id == user.id, IdempotencyKey.request_key == idempotency_key)
    ).scalar_one_or_none()
    if idem:
        return ok({"orderNo": idem.resource_id, "idempotent": True})

    # Validate address
    addr = db.get(UserAddress, req.addressId)
    if not addr or addr.user_id != user.id:
        raise ApiError(40024, "address not found", 400)

    # Get selected cart items
    items = db.execute(
        select(CartItem).where(CartItem.user_id == user.id, CartItem.id.in_(req.cartItemIds), CartItem.selected == True)
    ).scalars().all()
    if not items:
        raise ApiError(40022, "no selected cart items", 400)

    # Stock check
    for item in items:
        sku = db.get(ProductSku, item.sku_id)
        if not sku:
            raise ApiError(40025, f"sku {item.sku_id} not found", 400)
        if sku.stock < item.quantity:
            raise ApiError(40026, f"insufficient stock for sku {sku.sku_name}: need {item.quantity}, have {sku.stock}", 400)

    # Calculate price
    preview = _calc_preview(items, db)
    order_no = datetime.utcnow().strftime("%Y%m%d%H%M%S") + str(uuid.uuid4().int)[-6:]

    # Create order with address snapshot
    order = Order(
        order_no=order_no,
        user_id=user.id,
        address_id=addr.id,
        address_snapshot=_build_address_snapshot(addr),
        total_cent=preview["payableCent"],
        status="PENDING_PAYMENT",
    )
    db.add(order)
    db.flush()

    # Create order items with product snapshot + deduct stock
    for item in items:
        sku = db.get(ProductSku, item.sku_id)
        unit_price = sku.price_cent if sku else 0

        # Product snapshot
        product = db.get(Product, sku.product_id) if sku else None
        product_name = product.name if product else ""
        sku_name = sku.sku_name if sku else ""
        image_url = _get_product_image(sku.product_id, db) if sku else ""

        db.add(
            OrderItem(
                order_id=order.id,
                sku_id=item.sku_id,
                product_name=product_name,
                sku_name=sku_name,
                image_url=image_url,
                quantity=item.quantity,
                price_cent=unit_price,
            )
        )

        # Deduct stock
        if sku:
            sku.stock -= item.quantity

    # Price snapshot
    db.add(
        OrderPriceSnapshot(
            order_id=order.id,
            subtotal_cent=preview["subtotalCent"],
            shipping_cent=preview["shippingCent"],
            discount_cent=preview["discountCent"],
            payable_cent=preview["payableCent"],
        )
    )

    # Idempotency record
    db.add(
        IdempotencyKey(user_id=user.id, request_key=idempotency_key, resource_type="order", resource_id=order_no)
    )

    # Clear purchased cart items
    for item in items:
        db.delete(item)

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
    address = json.loads(o.address_snapshot) if o.address_snapshot else {}
    return ok(
        {
            "orderNo": o.order_no,
            "status": o.status,
            "totalCent": o.total_cent,
            "address": address,
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
        }
    )


def _restore_stock(order: Order, db: Session):
    """Restore stock for all items in the order."""
    order_items = db.execute(select(OrderItem).where(OrderItem.order_id == order.id)).scalars().all()
    for oi in order_items:
        sku = db.get(ProductSku, oi.sku_id)
        if sku:
            sku.stock += oi.quantity


@router.post("/{order_no}/cancel")
def cancel_order(order_no: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    o = db.execute(select(Order).where(Order.order_no == order_no, Order.user_id == user.id)).scalar_one_or_none()
    if not o:
        raise ApiError(40422, "order not found", 404)
    if o.status != "PENDING_PAYMENT":
        raise ApiError(40023, "order cannot be cancelled", 400)
    o.status = "CANCELED"
    _restore_stock(o, db)
    db.commit()
    return ok({"success": True})


@router.post("/{order_no}/ship")
def ship_order(order_no: str, db: Session = Depends(get_db)):
    """Mark an order as shipped (admin/internal use)."""
    o = db.execute(select(Order).where(Order.order_no == order_no)).scalar_one_or_none()
    if not o:
        raise ApiError(40423, "order not found", 404)
    if o.status != "PAID":
        raise ApiError(40027, "only paid orders can be shipped", 400)
    o.status = "SHIPPED"
    db.commit()
    return ok({"success": True})


@router.post("/{order_no}/confirm-delivery")
def confirm_delivery(order_no: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Buyer confirms receipt of goods."""
    o = db.execute(select(Order).where(Order.order_no == order_no, Order.user_id == user.id)).scalar_one_or_none()
    if not o:
        raise ApiError(40424, "order not found", 404)
    if o.status != "SHIPPED":
        raise ApiError(40028, "order is not in shipped status", 400)
    o.status = "COMPLETED"
    db.commit()
    return ok({"success": True})
