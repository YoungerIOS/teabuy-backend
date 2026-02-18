from pydantic import BaseModel
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.response import ok
from app.models import Order, Payment, User

router = APIRouter(prefix="/payments/mock", tags=["payment"])


class CreateMockPayReq(BaseModel):
    orderNo: str


class MockCallbackReq(BaseModel):
    orderNo: str
    success: bool = True


@router.post("/create")
def create_mock_payment(req: CreateMockPayReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if settings.payment_mode != "mock":
        raise ApiError(40031, "mock payment disabled", 400)
    order = db.execute(select(Order).where(Order.order_no == req.orderNo, Order.user_id == user.id)).scalar_one_or_none()
    if not order:
        raise ApiError(40431, "order not found", 404)
    p = Payment(order_id=order.id, provider="mock", status="PAYING", amount_cent=order.total_cent)
    db.add(p)
    db.commit()
    return ok({"paymentId": p.id, "payUrl": f"mock://pay/{p.id}"})


@router.post("/callback")
def mock_callback(req: MockCallbackReq, db: Session = Depends(get_db)):
    order = db.execute(select(Order).where(Order.order_no == req.orderNo)).scalar_one_or_none()
    if not order:
        raise ApiError(40432, "order not found", 404)
    payment = db.execute(select(Payment).where(Payment.order_id == order.id).order_by(Payment.created_at.desc())).scalar_one_or_none()
    if not payment:
        payment = Payment(order_id=order.id, provider="mock", amount_cent=order.total_cent)
        db.add(payment)
    payment.status = "SUCCESS" if req.success else "FAIL"
    order.status = "PAID" if req.success else order.status
    db.commit()
    return ok({"success": True})
