from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_admin
from app.core.errors import ApiError
from app.core.response import ok
from app.models import Category, Product, ProductMedia, ProductSku

router = APIRouter(prefix="/internal/catalog", tags=["internal-catalog"])

ALLOWED_PRODUCT_STATUSES = {"draft", "active", "inactive"}


class InternalCategoryCreatePayload(BaseModel):
    id: str | None = None
    name: str
    sort: int = 0


class InternalCategoryUpdatePayload(BaseModel):
    name: str
    sort: int = 0


class InternalProductCreatePayload(BaseModel):
    id: str | None = None
    name: str
    subtitle: str = ""
    categoryId: str
    description: str = ""
    marketPriceCent: int = Field(default=0, ge=0)
    soldCount: int = Field(default=0, ge=0)
    badgePrimary: str = ""
    badgeSecondary: str = ""
    status: str = "draft"


class InternalProductUpdatePayload(BaseModel):
    name: str
    subtitle: str = ""
    categoryId: str
    description: str = ""
    marketPriceCent: int = Field(default=0, ge=0)
    soldCount: int = Field(default=0, ge=0)
    badgePrimary: str = ""
    badgeSecondary: str = ""
    status: str = "draft"


class InternalProductStatusPayload(BaseModel):
    status: str


class InternalSkuItemPayload(BaseModel):
    id: str | None = None
    name: str
    priceCent: int = Field(ge=0)
    stock: int = Field(default=0, ge=0)


class InternalSkuReplacePayload(BaseModel):
    items: list[InternalSkuItemPayload]


class InternalMediaItemPayload(BaseModel):
    id: str | None = None
    url: str
    sort: int = 0


class InternalMediaReplacePayload(BaseModel):
    items: list[InternalMediaItemPayload]


def _check_product_status(status: str) -> str:
    clean = status.strip().lower()
    if clean not in ALLOWED_PRODUCT_STATUSES:
        raise ApiError(40071, "invalid product status", 400)
    return clean


def _as_internal_product_item(product: Product, min_price: int, total_stock: int, media_url: str = "") -> dict:
    return {
        "id": product.id,
        "name": product.name,
        "subtitle": product.subtitle,
        "categoryId": product.category_id,
        "description": product.description,
        "marketPriceCent": product.market_price_cent,
        "soldCount": product.sold_count,
        "badgePrimary": product.badge_primary,
        "badgeSecondary": product.badge_secondary,
        "status": product.status,
        "minPriceCent": min_price,
        "totalStock": total_stock,
        "coverImageUrl": media_url,
    }


@router.get("/categories")
def get_internal_categories(_: object = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.execute(select(Category).order_by(Category.sort_order.asc(), Category.name.asc())).scalars().all()
    return ok([{"id": c.id, "name": c.name, "sort": c.sort_order} for c in rows])


@router.post("/categories")
def create_internal_category(
    body: InternalCategoryCreatePayload,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    name = body.name.strip()
    if not name:
        raise ApiError(40072, "category name required", 400)

    existing_name = db.execute(select(Category).where(Category.name == name)).scalars().first()
    if existing_name:
        raise ApiError(40971, "category name already exists", 409)

    if body.id:
        exists = db.get(Category, body.id)
        if exists:
            raise ApiError(40972, "category id already exists", 409)
        category = Category(id=body.id, name=name, sort_order=body.sort)
    else:
        category = Category(name=name, sort_order=body.sort)

    db.add(category)
    db.commit()
    return ok({"id": category.id, "name": category.name, "sort": category.sort_order})


@router.put("/categories/{category_id}")
def update_internal_category(
    category_id: str,
    body: InternalCategoryUpdatePayload,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    category = db.get(Category, category_id)
    if not category:
        raise ApiError(40471, "category not found", 404)

    name = body.name.strip()
    if not name:
        raise ApiError(40072, "category name required", 400)

    duplicate = db.execute(select(Category).where(Category.name == name, Category.id != category_id)).scalars().first()
    if duplicate:
        raise ApiError(40971, "category name already exists", 409)

    category.name = name
    category.sort_order = body.sort
    db.commit()
    return ok({"id": category.id, "name": category.name, "sort": category.sort_order})


@router.get("/products")
def get_internal_products(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200, alias="pageSize"),
    status: str = "",
    category_id: str = Query(default="", alias="categoryId"),
    keyword: str = "",
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    price_subq = (
        select(
            ProductSku.product_id.label("product_id"),
            func.min(ProductSku.price_cent).label("min_price"),
            func.sum(ProductSku.stock).label("total_stock"),
        )
        .group_by(ProductSku.product_id)
        .subquery()
    )
    stmt = (
        select(Product, price_subq.c.min_price, price_subq.c.total_stock)
        .outerjoin(price_subq, price_subq.c.product_id == Product.id)
        .order_by(Product.id.desc())
    )

    clean_status = status.strip().lower()
    if clean_status:
        if clean_status not in ALLOWED_PRODUCT_STATUSES:
            raise ApiError(40071, "invalid product status", 400)
        stmt = stmt.where(Product.status == clean_status)

    if category_id.strip():
        stmt = stmt.where(Product.category_id == category_id.strip())

    clean_keyword = keyword.strip()
    if clean_keyword:
        stmt = stmt.where(or_(Product.name.like(f"%{clean_keyword}%"), Product.subtitle.like(f"%{clean_keyword}%")))

    rows = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    products = [row[0] for row in rows]
    product_ids = [p.id for p in products]

    media_map: dict[str, str] = {}
    if product_ids:
        medias = db.execute(
            select(ProductMedia).where(ProductMedia.product_id.in_(product_ids)).order_by(
                ProductMedia.product_id.asc(),
                ProductMedia.sort_order.asc(),
                ProductMedia.id.asc(),
            )
        ).scalars().all()
        for media in medias:
            if media.product_id not in media_map:
                media_map[media.product_id] = media.media_url

    items = []
    for product, min_price, total_stock in rows:
        items.append(
            _as_internal_product_item(
                product=product,
                min_price=int(min_price or 0),
                total_stock=int(total_stock or 0),
                media_url=media_map.get(product.id, ""),
            )
        )

    return ok({"page": page, "pageSize": page_size, "items": items})


@router.get("/products/{product_id}")
def get_internal_product_detail(product_id: str, _: object = Depends(require_admin), db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise ApiError(40472, "product not found", 404)

    skus = db.execute(
        select(ProductSku).where(ProductSku.product_id == product_id).order_by(ProductSku.price_cent.asc(), ProductSku.id.asc())
    ).scalars().all()
    medias = db.execute(
        select(ProductMedia)
        .where(ProductMedia.product_id == product_id)
        .order_by(ProductMedia.sort_order.asc(), ProductMedia.id.asc())
    ).scalars().all()

    min_price = skus[0].price_cent if skus else 0
    total_stock = sum(sku.stock for sku in skus) if skus else 0
    cover = medias[0].media_url if medias else ""
    base = _as_internal_product_item(product, min_price=min_price, total_stock=total_stock, media_url=cover)
    base["skus"] = [{"id": s.id, "name": s.sku_name, "priceCent": s.price_cent, "stock": s.stock} for s in skus]
    base["medias"] = [{"id": m.id, "url": m.media_url, "sort": m.sort_order} for m in medias]
    return ok(base)


@router.post("/products")
def create_internal_product(
    body: InternalProductCreatePayload,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    category = db.get(Category, body.categoryId)
    if not category:
        raise ApiError(40471, "category not found", 404)

    status = _check_product_status(body.status)
    name = body.name.strip()
    if not name:
        raise ApiError(40073, "product name required", 400)

    if body.id:
        exists = db.get(Product, body.id)
        if exists:
            raise ApiError(40973, "product id already exists", 409)
        product = Product(
            id=body.id,
            name=name,
            subtitle=body.subtitle.strip(),
            category_id=body.categoryId,
            description=body.description.strip(),
            market_price_cent=body.marketPriceCent,
            sold_count=body.soldCount,
            badge_primary=body.badgePrimary.strip(),
            badge_secondary=body.badgeSecondary.strip(),
            status=status,
        )
    else:
        product = Product(
            name=name,
            subtitle=body.subtitle.strip(),
            category_id=body.categoryId,
            description=body.description.strip(),
            market_price_cent=body.marketPriceCent,
            sold_count=body.soldCount,
            badge_primary=body.badgePrimary.strip(),
            badge_secondary=body.badgeSecondary.strip(),
            status=status,
        )

    db.add(product)
    db.commit()
    return ok({"id": product.id})


@router.put("/products/{product_id}")
def update_internal_product(
    product_id: str,
    body: InternalProductUpdatePayload,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)
    if not product:
        raise ApiError(40472, "product not found", 404)

    category = db.get(Category, body.categoryId)
    if not category:
        raise ApiError(40471, "category not found", 404)

    status = _check_product_status(body.status)
    name = body.name.strip()
    if not name:
        raise ApiError(40073, "product name required", 400)

    product.name = name
    product.subtitle = body.subtitle.strip()
    product.category_id = body.categoryId
    product.description = body.description.strip()
    product.market_price_cent = body.marketPriceCent
    product.sold_count = body.soldCount
    product.badge_primary = body.badgePrimary.strip()
    product.badge_secondary = body.badgeSecondary.strip()
    product.status = status
    db.commit()
    return ok({"updated": True, "id": product_id})


@router.patch("/products/{product_id}/status")
def patch_internal_product_status(
    product_id: str,
    body: InternalProductStatusPayload,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)
    if not product:
        raise ApiError(40472, "product not found", 404)
    product.status = _check_product_status(body.status)
    db.commit()
    return ok({"updated": True, "id": product_id, "status": product.status})


@router.put("/products/{product_id}/skus")
def put_internal_product_skus(
    product_id: str,
    body: InternalSkuReplacePayload,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)
    if not product:
        raise ApiError(40472, "product not found", 404)

    db.execute(delete(ProductSku).where(ProductSku.product_id == product_id))
    for idx, item in enumerate(body.items):
        if item.id:
            sku = ProductSku(
                id=item.id,
                product_id=product_id,
                sku_name=item.name.strip() or f"规格{idx + 1}",
                price_cent=item.priceCent,
                stock=item.stock,
            )
        else:
            sku = ProductSku(
                product_id=product_id,
                sku_name=item.name.strip() or f"规格{idx + 1}",
                price_cent=item.priceCent,
                stock=item.stock,
            )
        db.add(sku)
    db.commit()
    return ok({"updated": True, "count": len(body.items)})


@router.put("/products/{product_id}/media")
def put_internal_product_media(
    product_id: str,
    body: InternalMediaReplacePayload,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)
    if not product:
        raise ApiError(40472, "product not found", 404)

    db.execute(delete(ProductMedia).where(ProductMedia.product_id == product_id))
    for idx, item in enumerate(body.items):
        if item.id:
            media = ProductMedia(
                id=item.id,
                product_id=product_id,
                media_url=item.url.strip(),
                sort_order=item.sort,
            )
        else:
            media = ProductMedia(
                product_id=product_id,
                media_url=item.url.strip(),
                sort_order=item.sort if item.sort != 0 else idx + 1,
            )
        db.add(media)
    db.commit()
    return ok({"updated": True, "count": len(body.items)})


def _seed_category(spec: dict, db: Session) -> Category:
    by_name = db.execute(select(Category).where(Category.name == spec["name"])).scalars().first()
    if by_name:
        by_name.sort_order = spec["sort"]
        return by_name

    category = db.get(Category, spec["id"])
    if category:
        category.name = spec["name"]
        category.sort_order = spec["sort"]
        return category

    category = Category(id=spec["id"], name=spec["name"], sort_order=spec["sort"])
    db.add(category)
    return category


def _upsert_demo_product(spec: dict, category_id: str, db: Session):
    product = db.get(Product, spec["id"])
    if not product:
        product = Product(id=spec["id"], name=spec["name"], category_id=category_id)
        db.add(product)

    product.name = spec["name"]
    product.subtitle = spec.get("subtitle", "")
    product.category_id = category_id
    product.description = spec.get("description", "")
    product.market_price_cent = spec.get("marketPriceCent", 0)
    product.sold_count = spec.get("soldCount", 0)
    product.badge_primary = spec.get("badgePrimary", "")
    product.badge_secondary = spec.get("badgeSecondary", "")
    product.status = "active"

    db.execute(delete(ProductSku).where(ProductSku.product_id == spec["id"]))
    db.execute(delete(ProductMedia).where(ProductMedia.product_id == spec["id"]))
    for idx, sku in enumerate(spec.get("skus", [])):
        db.add(
            ProductSku(
                id=f"{spec['id']}_sku_{idx + 1}",
                product_id=spec["id"],
                sku_name=sku["name"],
                price_cent=sku["priceCent"],
                stock=sku["stock"],
            )
        )
    for idx, media in enumerate(spec.get("medias", [])):
        db.add(
            ProductMedia(
                id=f"{spec['id']}_media_{idx + 1}",
                product_id=spec["id"],
                media_url=media["url"],
                sort_order=media["sort"],
            )
        )


@router.post("/demo-seed")
def post_internal_catalog_demo_seed(_: object = Depends(require_admin), db: Session = Depends(get_db)):
    categories = [
        {"id": "cat_tea_bag", "key": "tea_bag", "name": "袋茶", "sort": 1},
        {"id": "cat_tea_pack", "key": "tea_pack", "name": "包茶", "sort": 2},
        {"id": "cat_teaware", "key": "teaware", "name": "茶具", "sort": 3},
        {"id": "cat_tea_product", "key": "tea_product", "name": "茶制品", "sort": 4},
    ]
    category_id_by_key: dict[str, str] = {}
    for spec in categories:
        category = _seed_category(spec, db)
        category_id_by_key[spec["key"]] = category.id

    products = [
        {
            "id": "featured_boutique_1",
            "name": "高山绿茶",
            "subtitle": "清香回甘",
            "categoryKey": "tea_pack",
            "marketPriceCent": 15900,
            "soldCount": 320,
            "badgePrimary": "新品",
            "badgeSecondary": "热销",
            "skus": [{"name": "250g", "priceCent": 12900, "stock": 80}],
            "medias": [{"url": "https://nfzznasyztaontqmuhjq.supabase.co/storage/v1/object/public/product-images/home/home_new_tea_1.png", "sort": 1}],
        },
        {
            "id": "featured_boutique_2",
            "name": "银针绿茶",
            "subtitle": "芽头鲜嫩",
            "categoryKey": "tea_pack",
            "marketPriceCent": 19900,
            "soldCount": 265,
            "badgePrimary": "口碑",
            "badgeSecondary": "推荐",
            "skus": [{"name": "250g", "priceCent": 16800, "stock": 74}],
            "medias": [{"url": "https://nfzznasyztaontqmuhjq.supabase.co/storage/v1/object/public/product-images/home/home_new_tea_2.png", "sort": 1}],
        },
        {
            "id": "featured_boutique_3",
            "name": "菊花茶",
            "subtitle": "花香清润",
            "categoryKey": "tea_bag",
            "marketPriceCent": 12800,
            "soldCount": 490,
            "badgePrimary": "回购高",
            "badgeSecondary": "轻养生",
            "skus": [{"name": "20袋", "priceCent": 9800, "stock": 120}],
            "medias": [{"url": "https://nfzznasyztaontqmuhjq.supabase.co/storage/v1/object/public/product-images/home/home_review_bg_2.png", "sort": 1}],
        },
        {
            "id": "featured_boutique_4",
            "name": "红茶",
            "subtitle": "醇厚顺滑",
            "categoryKey": "tea_pack",
            "marketPriceCent": 13800,
            "soldCount": 401,
            "badgePrimary": "经典",
            "badgeSecondary": "常备",
            "skus": [{"name": "250g", "priceCent": 11800, "stock": 92}],
            "medias": [{"url": "https://nfzznasyztaontqmuhjq.supabase.co/storage/v1/object/public/product-images/home/home_review_bg_1.png", "sort": 1}],
        },
        {
            "id": "featured_list_1_a",
            "name": "碧螺春",
            "subtitle": "嫩香鲜醇",
            "categoryKey": "tea_pack",
            "marketPriceCent": 14900,
            "soldCount": 550,
            "badgePrimary": "人气",
            "badgeSecondary": "热销",
            "skus": [{"name": "250g", "priceCent": 11400, "stock": 66}],
            "medias": [{"url": "https://nfzznasyztaontqmuhjq.supabase.co/storage/v1/object/public/product-images/home/home_review_bg_1.png", "sort": 1}],
        },
        {
            "id": "featured_list_1_b",
            "name": "白毛豪尖",
            "subtitle": "毫香馥郁",
            "categoryKey": "tea_pack",
            "marketPriceCent": 9900,
            "soldCount": 211,
            "badgePrimary": "限时",
            "badgeSecondary": "折扣",
            "skus": [{"name": "200g", "priceCent": 5300, "stock": 52}],
            "medias": [{"url": "https://nfzznasyztaontqmuhjq.supabase.co/storage/v1/object/public/product-images/home/home_review_bg_2.png", "sort": 1}],
        },
        {
            "id": "featured_list_2_a",
            "name": "花茶",
            "subtitle": "甘甜清雅",
            "categoryKey": "tea_bag",
            "marketPriceCent": 13200,
            "soldCount": 372,
            "badgePrimary": "新品",
            "badgeSecondary": "月销优选",
            "skus": [{"name": "20袋", "priceCent": 11800, "stock": 90}],
            "medias": [{"url": "https://nfzznasyztaontqmuhjq.supabase.co/storage/v1/object/public/product-images/home/home_review_bg_6.png", "sort": 1}],
        },
        {
            "id": "featured_list_2_b",
            "name": "白茶",
            "subtitle": "清甜耐泡",
            "categoryKey": "tea_pack",
            "marketPriceCent": 8800,
            "soldCount": 188,
            "badgePrimary": "经典",
            "badgeSecondary": "口碑好评",
            "skus": [{"name": "200g", "priceCent": 5500, "stock": 57}],
            "medias": [{"url": "https://nfzznasyztaontqmuhjq.supabase.co/storage/v1/object/public/product-images/home/home_review_bg_7.png", "sort": 1}],
        },
    ]

    for spec in products:
        category_id = category_id_by_key[spec["categoryKey"]]
        _upsert_demo_product(spec, category_id, db)

    db.commit()
    return ok(
        {
            "seededCategories": len(categories),
            "seededProducts": len(products),
            "seededAt": datetime.now(timezone.utc).isoformat(),
        }
    )
