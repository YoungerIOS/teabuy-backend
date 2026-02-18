from pydantic import BaseModel
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.response import ok
from app.models import User, UserAddress

router = APIRouter(prefix="/addresses", tags=["address"])


class AddressReq(BaseModel):
    recipient: str
    phone: str
    region: str
    detail: str


@router.get("")
def list_addresses(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(UserAddress).where(UserAddress.user_id == user.id)).scalars().all()
    return ok([
        {
            "id": a.id,
            "recipient": a.recipient,
            "phone": a.phone,
            "region": a.region,
            "detail": a.detail,
            "isDefault": a.is_default,
        }
        for a in rows
    ])


@router.post("")
def create_address(req: AddressReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    addr = UserAddress(user_id=user.id, recipient=req.recipient, phone=req.phone, region=req.region, detail=req.detail)
    db.add(addr)
    db.commit()
    return ok({"id": addr.id})


@router.patch("/{address_id}")
def update_address(address_id: str, req: AddressReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    addr = db.get(UserAddress, address_id)
    if not addr or addr.user_id != user.id:
        raise ApiError(40411, "address not found", 404)
    addr.recipient, addr.phone, addr.region, addr.detail = req.recipient, req.phone, req.region, req.detail
    db.commit()
    return ok({"success": True})


@router.delete("/{address_id}")
def delete_address(address_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    addr = db.get(UserAddress, address_id)
    if not addr or addr.user_id != user.id:
        raise ApiError(40412, "address not found", 404)
    db.delete(addr)
    db.commit()
    return ok({"success": True})


@router.post("/{address_id}/default")
def set_default(address_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(UserAddress).where(UserAddress.user_id == user.id)).scalars().all()
    found = False
    for a in rows:
        a.is_default = a.id == address_id
        if a.id == address_id:
            found = True
    if not found:
        raise ApiError(40413, "address not found", 404)
    db.commit()
    return ok({"success": True})
