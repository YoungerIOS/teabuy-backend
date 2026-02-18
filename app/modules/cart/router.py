from pydantic import BaseModel
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.response import ok
from app.models import CartItem, ProductSku, User

router = APIRouter(prefix="/cart", tags=["cart"])


class AddCartReq(BaseModel):
    skuId: str
    quantity: int = 1


class UpdateCartReq(BaseModel):
    quantity: int
    selected: bool | None = None


class BatchSelectReq(BaseModel):
    itemIds: list[str]
    selected: bool


@router.get("")
def get_cart(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(CartItem).where(CartItem.user_id == user.id)).scalars().all()
    items = []
    total_cent = 0
    for it in rows:
        sku = db.get(ProductSku, it.sku_id)
        price = sku.price_cent if sku else 0
        subtotal = price * it.quantity
        if it.selected:
            total_cent += subtotal
        items.append(
            {
                "id": it.id,
                "skuId": it.sku_id,
                "quantity": it.quantity,
                "selected": it.selected,
                "unitPriceCent": price,
                "subtotalCent": subtotal,
            }
        )
    return ok({"items": items, "totalCent": total_cent})


@router.post("/items")
def add_item(req: AddCartReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sku = db.get(ProductSku, req.skuId)
    if not sku:
        raise ApiError(40401, "sku not found", 404)
    existed = db.execute(
        select(CartItem).where(CartItem.user_id == user.id, CartItem.sku_id == req.skuId)
    ).scalar_one_or_none()
    if existed:
        existed.quantity += req.quantity
    else:
        db.add(CartItem(user_id=user.id, sku_id=req.skuId, quantity=req.quantity, selected=True))
    db.commit()
    return ok({"success": True})


@router.patch("/items/{item_id}")
def patch_item(item_id: str, req: UpdateCartReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(CartItem, item_id)
    if not item or item.user_id != user.id:
        raise ApiError(40402, "cart item not found", 404)
    item.quantity = req.quantity
    if req.selected is not None:
        item.selected = req.selected
    db.commit()
    return ok({"success": True})


@router.delete("/items/{item_id}")
def delete_item(item_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(CartItem, item_id)
    if not item or item.user_id != user.id:
        raise ApiError(40403, "cart item not found", 404)
    db.delete(item)
    db.commit()
    return ok({"success": True})


@router.post("/items/select")
def batch_select(req: BatchSelectReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(CartItem).where(CartItem.user_id == user.id, CartItem.id.in_(req.itemIds))).scalars().all()
    for r in rows:
        r.selected = req.selected
    db.commit()
    return ok({"success": True})
