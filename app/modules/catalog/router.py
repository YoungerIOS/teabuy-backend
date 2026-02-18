from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.response import ok
from app.models import Category, Product, ProductSku

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/categories")
def categories(db: Session = Depends(get_db)):
    rows = db.execute(select(Category).order_by(Category.sort_order.asc())).scalars().all()
    return ok([{"id": c.id, "name": c.name} for c in rows])


@router.get("/filters")
def filters():
    return ok({"sortOptions": ["default", "priceAsc", "priceDesc"], "priceRanges": ["0-5000", "5000-20000"]})


@router.get("/products")
def products(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    category_id: str = "",
    db: Session = Depends(get_db),
):
    stmt = select(Product)
    if category_id:
        stmt = stmt.where(Product.category_id == category_id)
    items = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    result = [{"id": p.id, "name": p.name, "categoryId": p.category_id, "status": p.status} for p in items]
    return ok({"page": page, "pageSize": page_size, "items": result})


@router.get("/products/{product_id}")
def product_detail(product_id: str, db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if not p:
        return ok({})
    skus = db.execute(select(ProductSku).where(ProductSku.product_id == p.id)).scalars().all()
    return ok(
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "skus": [{"id": s.id, "name": s.sku_name, "priceCent": s.price_cent, "stock": s.stock} for s in skus],
        }
    )
