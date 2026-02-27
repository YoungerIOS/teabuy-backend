from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.response import ok
from app.models import Order, OrderItem, ProductSku, Refund, User

router = APIRouter(prefix="/refunds", tags=["refund"])


class CreateRefundReq(BaseModel):
    orderNo: str
    reason: str = ""


@router.post("")
def create_refund(req: CreateRefundReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.execute(
        select(Order).where(Order.order_no == req.orderNo, Order.user_id == user.id)
    ).scalar_one_or_none()
    if not order:
        raise ApiError(40451, "order not found", 404)
    if order.status != "PAID":
        raise ApiError(40041, "only paid orders can be refunded", 400)

    # Prevent duplicate refund
    existing = db.execute(
        select(Refund).where(Refund.order_id == order.id, Refund.status == "PENDING")
    ).scalar_one_or_none()
    if existing:
        raise ApiError(40042, "a pending refund already exists", 400)

    refund = Refund(
        order_id=order.id,
        user_id=user.id,
        reason=req.reason,
        amount_cent=order.total_cent,
        status="PENDING",
    )
    order.status = "REFUNDING"
    db.add(refund)
    db.commit()
    return ok({"refundId": refund.id})


@router.post("/{refund_id}/approve")
def approve_refund(refund_id: str, db: Session = Depends(get_db)):
    """Admin approves refund request."""
    refund = db.get(Refund, refund_id)
    if not refund:
        raise ApiError(40452, "refund not found", 404)
    if refund.status != "PENDING":
        raise ApiError(40043, "refund is not in pending status", 400)

    refund.status = "APPROVED"

    # Update order status
    order = db.execute(select(Order).where(Order.id == refund.order_id)).scalar_one_or_none()
    if order:
        order.status = "REFUNDED"
        # Restore stock
        order_items = db.execute(select(OrderItem).where(OrderItem.order_id == order.id)).scalars().all()
        for oi in order_items:
            sku = db.get(ProductSku, oi.sku_id)
            if sku:
                sku.stock += oi.quantity

    db.commit()
    return ok({"success": True})


@router.post("/{refund_id}/reject")
def reject_refund(refund_id: str, db: Session = Depends(get_db)):
    """Admin rejects refund request."""
    refund = db.get(Refund, refund_id)
    if not refund:
        raise ApiError(40453, "refund not found", 404)
    if refund.status != "PENDING":
        raise ApiError(40044, "refund is not in pending status", 400)

    refund.status = "REJECTED"

    # Revert order status back to PAID
    order = db.execute(select(Order).where(Order.id == refund.order_id)).scalar_one_or_none()
    if order and order.status == "REFUNDING":
        order.status = "PAID"

    db.commit()
    return ok({"success": True})


@router.get("")
def list_refunds(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Refund).where(Refund.user_id == user.id).order_by(Refund.created_at.desc())
    ).scalars().all()
    return ok(
        [
            {
                "id": r.id,
                "orderId": r.order_id,
                "reason": r.reason,
                "amountCent": r.amount_cent,
                "status": r.status,
                "createdAt": r.created_at.isoformat(),
            }
            for r in rows
        ]
    )
