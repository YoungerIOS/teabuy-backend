from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.response import ok
from app.models import User, UserAddress
from app.services.china_area import get_cities, get_districts, get_provinces, load_china_area_tree

router = APIRouter(prefix="/addresses", tags=["address"])


class AddressReq(BaseModel):
    recipient: str
    phone: str
    region: str
    detail: str


@router.get("/china/areas")
def china_area_tree():
    return ok(load_china_area_tree())


@router.get("/china/provinces")
def china_provinces():
    provinces = get_provinces()
    return ok([{"adcode": p["adcode"], "name": p["name"], "center": p["center"]} for p in provinces])


@router.get("/china/cities")
def china_cities(province_adcode: str = Query(default="")):
    if not province_adcode:
        raise ApiError(40014, "province_adcode is required", 400)
    cities = get_cities(province_adcode)
    return ok([{"adcode": c["adcode"], "name": c["name"], "center": c["center"]} for c in cities])


@router.get("/china/districts")
def china_districts(city_adcode: str = Query(default="")):
    if not city_adcode:
        raise ApiError(40015, "city_adcode is required", 400)
    districts = get_districts(city_adcode)
    return ok([{"adcode": d["adcode"], "name": d["name"], "center": d["center"]} for d in districts])


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


@router.get("/default")
def get_default_address(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    addr = db.execute(
        select(UserAddress).where(UserAddress.user_id == user.id, UserAddress.is_default == True)
    ).scalars().first()
    if not addr:
        return ok({})
    return ok(
        {
            "id": addr.id,
            "recipient": addr.recipient,
            "phone": addr.phone,
            "region": addr.region,
            "detail": addr.detail,
            "isDefault": addr.is_default,
        }
    )


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
