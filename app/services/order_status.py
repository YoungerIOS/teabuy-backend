from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Order, OrderStatusLog


def log_order_status_change(
    db: Session,
    order: Order,
    to_status: str,
    operator_id: str = "",
    operator_role: str = "",
    reason: str = "",
) -> None:
    from_status = order.status
    if from_status == to_status:
        return
    order.status = to_status
    order.updated_at = datetime.utcnow()
    db.add(
        OrderStatusLog(
            order_id=order.id,
            from_status=from_status,
            to_status=to_status,
            operator_id=operator_id,
            operator_role=operator_role,
            reason=reason,
        )
    )
