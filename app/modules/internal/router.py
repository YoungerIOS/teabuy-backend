from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.response import ok
from app.models import Order

router = APIRouter(prefix="/internal", tags=["internal"])


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
