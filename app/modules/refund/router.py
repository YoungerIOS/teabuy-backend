from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_admin
from app.core.errors import ApiError
from app.core.response import ok
from app.models import Order, OrderItem, ProductSku, Refund, User
from app.services.order_status import log_order_status_change

router = APIRouter(prefix="/refunds", tags=["refund"])


class CreateRefundReq(BaseModel):
    orderNo: str
    reason: str = ""


class RejectRefundReq(BaseModel):
    reason: str = ""


@router.post("")
def create_refund(req: CreateRefundReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.execute(
        select(Order).where(Order.order_no == req.orderNo, Order.user_id == user.id)
    ).scalar_one_or_none()
    if not order:
        raise ApiError(40451, "order not found", 404)
    if order.status not in {"PAID", "SHIPPED", "COMPLETED"}:
        raise ApiError(40041, "only paid/shipped/completed orders can be refunded", 400)

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
    log_order_status_change(db, order, "REFUNDING", operator_id=user.id, operator_role=user.role, reason="refund_apply")
    db.add(refund)
    db.commit()
    return ok({"refundId": refund.id})


@router.post("/{refund_id}/approve")
def approve_refund(refund_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Admin approves refund request."""
    refund = db.get(Refund, refund_id)
    if not refund:
        raise ApiError(40452, "refund not found", 404)
    if refund.status != "PENDING":
        raise ApiError(40043, "refund is not in pending status", 400)

    refund.status = "APPROVED"
    refund.reviewed_by = admin.id
    refund.reviewed_at = datetime.utcnow()
    refund.reject_reason = ""

    # Update order status
    order = db.execute(select(Order).where(Order.id == refund.order_id)).scalar_one_or_none()
    if order:
        log_order_status_change(db, order, "REFUNDED", operator_id=admin.id, operator_role=admin.role, reason="refund_approve")
        # Restore stock
        order_items = db.execute(select(OrderItem).where(OrderItem.order_id == order.id)).scalars().all()
        for oi in order_items:
            sku = db.get(ProductSku, oi.sku_id)
            if sku:
                sku.stock += oi.quantity

    db.commit()
    return ok({"success": True})


@router.post("/{refund_id}/reject")
def reject_refund(
    refund_id: str,
    body: RejectRefundReq,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin rejects refund request."""
    refund = db.get(Refund, refund_id)
    if not refund:
        raise ApiError(40453, "refund not found", 404)
    if refund.status != "PENDING":
        raise ApiError(40044, "refund is not in pending status", 400)

    refund.status = "REJECTED"
    refund.reviewed_by = admin.id
    refund.reviewed_at = datetime.utcnow()
    refund.reject_reason = body.reason

    # Revert order status back to PAID
    order = db.execute(select(Order).where(Order.id == refund.order_id)).scalar_one_or_none()
    if order and order.status == "REFUNDING":
        log_order_status_change(db, order, "PAID", operator_id=admin.id, operator_role=admin.role, reason="refund_reject")

    db.commit()
    return ok({"success": True})


@router.get("/{refund_id}")
def refund_detail(refund_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    refund = db.get(Refund, refund_id)
    if not refund or refund.user_id != user.id:
        raise ApiError(40454, "refund not found", 404)
    return ok(
        {
            "id": refund.id,
            "orderId": refund.order_id,
            "reason": refund.reason,
            "amountCent": refund.amount_cent,
            "status": refund.status,
            "reviewedBy": refund.reviewed_by,
            "reviewedAt": refund.reviewed_at.isoformat() if refund.reviewed_at else "",
            "rejectReason": refund.reject_reason,
            "createdAt": refund.created_at.isoformat(),
        }
    )


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
                "reviewedBy": r.reviewed_by,
                "reviewedAt": r.reviewed_at.isoformat() if r.reviewed_at else "",
                "rejectReason": r.reject_reason,
                "createdAt": r.created_at.isoformat(),
            }
            for r in rows
        ]
    )
