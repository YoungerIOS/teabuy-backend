from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.response import ok
from app.models import CartItem, Notification, Order, User

router = APIRouter(prefix="/me", tags=["profile"])


@router.get("/overview")
def overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order_count = db.query(Order).filter(Order.user_id == user.id).count()
    cart_count = db.query(CartItem).filter(CartItem.user_id == user.id).count()
    unread_count = db.query(Notification).filter(Notification.user_id == user.id, Notification.is_read == False).count()
    return ok(
        {
            "user": {"id": user.id, "username": user.username, "displayName": user.display_name},
            "orderCount": order_count,
            "cartCount": cart_count,
            "unreadCount": unread_count,
        }
    )
