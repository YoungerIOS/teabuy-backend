import hashlib
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.response import ok
from app.models import Order, Payment, User
from app.services.order_status import log_order_status_change

router = APIRouter(prefix="/payments/mock", tags=["payment"])


class CreateMockPayReq(BaseModel):
    orderNo: str


class MockCallbackReq(BaseModel):
    orderNo: str
    callbackNo: str = ""
    success: bool = True
    signature: str = ""


class MockPayNowReq(BaseModel):
    orderNo: str
    success: bool = True


def _build_signature(order_no: str, callback_no: str, success: bool) -> str:
    raw = f"{order_no}:{callback_no}:{int(success)}:{settings.mock_payment_callback_secret}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@router.post("/create")
def create_mock_payment(req: CreateMockPayReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if settings.payment_mode != "mock":
        raise ApiError(40031, "mock payment disabled", 400)
    order = db.execute(select(Order).where(Order.order_no == req.orderNo, Order.user_id == user.id)).scalar_one_or_none()
    if not order:
        raise ApiError(40431, "order not found", 404)
    if order.status != "PENDING_PAYMENT":
        raise ApiError(40032, "order is not payable", 400)
    p = Payment(order_id=order.id, provider="mock", status="PAYING", amount_cent=order.total_cent)
    db.add(p)
    db.commit()
    return ok({"paymentId": p.id, "payUrl": f"mock://pay/{p.id}"})


@router.post("/callback")
def mock_callback(req: MockCallbackReq, db: Session = Depends(get_db)):
    if not req.callbackNo:
        raise ApiError(40033, "callbackNo is required", 400)
    expected_sign = _build_signature(req.orderNo, req.callbackNo, req.success)
    if req.signature != expected_sign:
        raise ApiError(40131, "invalid callback signature", 401)

    order = db.execute(select(Order).where(Order.order_no == req.orderNo)).scalar_one_or_none()
    if not order:
        raise ApiError(40432, "order not found", 404)
    payment = db.execute(select(Payment).where(Payment.order_id == order.id).order_by(Payment.created_at.desc())).scalar_one_or_none()
    if not payment:
        payment = Payment(order_id=order.id, provider="mock", amount_cent=order.total_cent, status="PAYING")
        db.add(payment)
        db.flush()

    if payment.callback_no == req.callbackNo:
        return ok({"success": True, "idempotent": True})

    payment.callback_no = req.callbackNo
    payment.callback_payload = json.dumps(req.model_dump(), ensure_ascii=False)
    payment.updated_at = datetime.utcnow()
    payment.status = "SUCCESS" if req.success else "FAIL"

    if req.success and order.status == "PENDING_PAYMENT":
        log_order_status_change(db, order, "PAID", reason="payment_callback")

    db.commit()
    return ok({"success": True, "idempotent": False})


@router.post("/pay")
def mock_pay_now(req: MockPayNowReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if settings.payment_mode != "mock":
        raise ApiError(40031, "mock payment disabled", 400)

    order = db.execute(select(Order).where(Order.order_no == req.orderNo, Order.user_id == user.id)).scalar_one_or_none()
    if not order:
        raise ApiError(40431, "order not found", 404)

    if order.status != "PENDING_PAYMENT" and req.success:
        return ok({"success": True, "idempotent": True, "status": order.status})

    payment = db.execute(select(Payment).where(Payment.order_id == order.id).order_by(Payment.created_at.desc())).scalar_one_or_none()
    if not payment:
        payment = Payment(order_id=order.id, provider="mock", amount_cent=order.total_cent, status="PAYING")
        db.add(payment)
        db.flush()

    callback_no = f"mockpay-{uuid.uuid4()}"
    payment.callback_no = callback_no
    payload = {"orderNo": req.orderNo, "callbackNo": callback_no, "success": req.success, "signature": ""}
    payment.callback_payload = json.dumps(payload, ensure_ascii=False)
    payment.updated_at = datetime.utcnow()
    payment.status = "SUCCESS" if req.success else "FAIL"

    if req.success and order.status == "PENDING_PAYMENT":
        log_order_status_change(db, order, "PAID", reason="mock_pay_now")

    db.commit()
    return ok({"success": req.success, "idempotent": False, "status": order.status})
