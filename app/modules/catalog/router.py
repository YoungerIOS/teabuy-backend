from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.cache import TTLCache
from app.core.db import get_db
from app.core.response import ok
from app.models import Category, Product, ProductMedia, ProductSku

router = APIRouter(prefix="/catalog", tags=["catalog"])

CATEGORY_CACHE_TTL = 60
FILTERS_CACHE_TTL = 60
PRODUCT_LIST_CACHE_TTL = 30
PRODUCT_DETAIL_CACHE_TTL = 30
CACHE = TTLCache(default_ttl=30, max_size=2048)


CATEGORY_KEY_NAME_MAP = {
    "tea_bag": "袋茶",
    "tea_pack": "包茶",
    "teaware": "茶具",
    "tea_product": "茶制品",
    "tea_region": "茶区",
}

CATEGORY_KEY_ID_MAP = {
    "tea_bag": "cat_tea_bag",
    "tea_pack": "cat_tea_pack",
    "teaware": "cat_teaware",
    "tea_product": "cat_tea_product",
    "tea_region": "cat_tea_region",
}


def _price_text(price_cent: int) -> str:
    return f"￥{price_cent / 100:.2f}"


def _primary_image(product_id: str, db: Session) -> str:
    media = db.execute(
        select(ProductMedia).where(ProductMedia.product_id == product_id).order_by(ProductMedia.sort_order.asc())
    ).scalars().first()
    return media.media_url if media else ""


def _resolve_category_ids_by_key(category_key: str, db: Session) -> list[str]:
    if not category_key:
        return []
    clean_key = category_key.strip()
    if not clean_key:
        return []

    # 1) Prefer ID-based resolution so category renames do not break links.
    candidate_ids = [clean_key]
    mapped_id = CATEGORY_KEY_ID_MAP.get(clean_key)
    if mapped_id:
        candidate_ids.append(mapped_id)
    id_rows = db.execute(select(Category.id).where(Category.id.in_(candidate_ids))).scalars().all()
    if id_rows:
        return list(dict.fromkeys(id_rows))

    # 2) Fallback to name matching for legacy data.
    candidate_names = [clean_key]
    mapped_name = CATEGORY_KEY_NAME_MAP.get(clean_key)
    if mapped_name and mapped_name not in candidate_names:
        candidate_names.append(mapped_name)
    name_rows = db.execute(select(Category.id).where(Category.name.in_(candidate_names))).scalars().all()
    return list(dict.fromkeys(name_rows))


@router.get("/categories")
def categories(db: Session = Depends(get_db)):
    cache_key = ("catalog_categories",)
    cached = CACHE.get(cache_key)
    if cached is not None:
        return ok(cached)
    rows = db.execute(select(Category).order_by(Category.sort_order.asc())).scalars().all()
    data = [{"id": c.id, "name": c.name} for c in rows]
    CACHE.set(cache_key, data, CATEGORY_CACHE_TTL)
    return ok(data)


@router.get("/filters")
def filters():
    cache_key = ("catalog_filters",)
    cached = CACHE.get(cache_key)
    if cached is not None:
        return ok(cached)
    data = {"sortOptions": ["default", "priceAsc", "priceDesc"], "priceRanges": ["0-5000", "5000-20000"]}
    CACHE.set(cache_key, data, FILTERS_CACHE_TTL)
    return ok(data)


@router.get("/products")
def products(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    category_id: str = "",
    category_key: str = Query(default="", alias="categoryKey"),
    keyword: str = "",
    sort: str = "default",
    price_min: int | None = Query(default=None, alias="priceMin", ge=0),
    price_max: int | None = Query(default=None, alias="priceMax", ge=0),
    activity_key: str = Query(default="", alias="activityKey"),
    topic_key: str = Query(default="", alias="topicKey"),
    db: Session = Depends(get_db),
):
    cache_key = (
        "catalog_products",
        page,
        page_size,
        category_id,
        category_key,
        keyword,
        sort,
        price_min,
        price_max,
        activity_key,
        topic_key,
    )
    cached = CACHE.get(cache_key)
    if cached is not None:
        return ok(cached)
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
        .where(Product.status == "active")
    )

    if category_id:
        stmt = stmt.where(Product.category_id == category_id)
    elif category_key:
        category_ids = _resolve_category_ids_by_key(category_key, db)
        if not category_ids:
            data = {"page": page, "pageSize": page_size, "items": []}
            CACHE.set(cache_key, data, PRODUCT_LIST_CACHE_TTL)
            return ok(data)
        stmt = stmt.where(Product.category_id.in_(category_ids))

    if keyword:
        stmt = stmt.where(or_(Product.name.like(f"%{keyword}%"), Product.subtitle.like(f"%{keyword}%")))

    if activity_key:
        stmt = stmt.where(
            or_(
                Product.badge_primary.like(f"%{activity_key}%"),
                Product.badge_secondary.like(f"%{activity_key}%"),
                Product.subtitle.like(f"%{activity_key}%"),
            )
        )

    if topic_key:
        stmt = stmt.where(or_(Product.name.like(f"%{topic_key}%"), Product.subtitle.like(f"%{topic_key}%")))

    if price_min is not None:
        stmt = stmt.where(price_subq.c.min_price >= price_min)
    if price_max is not None:
        stmt = stmt.where(price_subq.c.min_price <= price_max)

    sort_key = sort.strip()
    if sort_key == "sales":
        stmt = stmt.order_by(Product.sold_count.desc(), Product.id.desc())
    elif sort_key == "priceAsc":
        stmt = stmt.order_by(func.coalesce(price_subq.c.min_price, 10**9).asc(), Product.id.desc())
    elif sort_key == "priceDesc":
        stmt = stmt.order_by(func.coalesce(price_subq.c.min_price, 0).desc(), Product.id.desc())
    elif sort_key == "newest":
        stmt = stmt.order_by(Product.id.desc())
    else:
        stmt = stmt.order_by(Product.sold_count.desc(), Product.id.desc())

    rows = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    items = [row[0] for row in rows]
    if not items:
        data = {"page": page, "pageSize": page_size, "items": []}
        CACHE.set(cache_key, data, PRODUCT_LIST_CACHE_TTL)
        return ok(data)

    product_ids = [p.id for p in items]
    price_map: dict[str, tuple[int, int]] = {}
    for row in rows:
        product, min_price, total_stock = row
        price_map[product.id] = (int(min_price or 0), int(total_stock or 0))

    medias = db.execute(
        select(ProductMedia).where(ProductMedia.product_id.in_(product_ids)).order_by(
            ProductMedia.product_id.asc(),
            ProductMedia.sort_order.asc(),
            ProductMedia.id.asc(),
        )
    ).scalars().all()
    image_map: dict[str, str] = {}
    for media in medias:
        if media.product_id not in image_map:
            image_map[media.product_id] = media.media_url

    skus = db.execute(
        select(ProductSku)
        .where(ProductSku.product_id.in_(product_ids))
        .order_by(ProductSku.product_id.asc(), ProductSku.price_cent.asc(), ProductSku.id.asc())
    ).scalars().all()
    default_sku_map: dict[str, str] = {}
    for sku in skus:
        if sku.product_id not in default_sku_map:
            default_sku_map[sku.product_id] = sku.id

    result = []
    for p in items:
        price_cent, stock = price_map.get(p.id, (0, 0))
        result.append(
            {
                "id": p.id,
                "name": p.name,
                "subtitle": p.subtitle,
                "categoryId": p.category_id,
                "imageUrl": image_map.get(p.id, ""),
                "defaultSkuId": default_sku_map.get(p.id, ""),
                "priceCent": price_cent,
                "priceText": _price_text(price_cent),
                "marketPriceCent": p.market_price_cent,
                "soldCount": p.sold_count,
                "badgePrimary": p.badge_primary,
                "badgeSecondary": p.badge_secondary,
                "status": p.status,
                "stock": stock,
            }
        )
    data = {"page": page, "pageSize": page_size, "items": result}
    CACHE.set(cache_key, data, PRODUCT_LIST_CACHE_TTL)
    return ok(data)


@router.get("/products/{product_id}")
def product_detail(product_id: str, db: Session = Depends(get_db)):
    cache_key = ("catalog_product_detail", product_id)
    cached = CACHE.get(cache_key)
    if cached is not None:
        return ok(cached)
    p = db.get(Product, product_id)
    if not p:
        data = {}
        CACHE.set(cache_key, data, PRODUCT_DETAIL_CACHE_TTL)
        return ok(data)

    medias = db.execute(
        select(ProductMedia).where(ProductMedia.product_id == p.id).order_by(ProductMedia.sort_order.asc())
    ).scalars().all()
    skus = db.execute(
        select(ProductSku).where(ProductSku.product_id == p.id).order_by(ProductSku.price_cent.asc())
    ).scalars().all()
    recommend = db.execute(
        select(Product).where(Product.category_id == p.category_id, Product.id != p.id, Product.status == "active").limit(6)
    ).scalars().all()

    rec_ids = [r.id for r in recommend]
    rec_image_map: dict[str, str] = {}
    rec_price_map: dict[str, int] = {}
    if rec_ids:
        rec_medias = db.execute(
            select(ProductMedia)
            .where(ProductMedia.product_id.in_(rec_ids))
            .order_by(ProductMedia.product_id.asc(), ProductMedia.sort_order.asc(), ProductMedia.id.asc())
        ).scalars().all()
        for media in rec_medias:
            if media.product_id not in rec_image_map:
                rec_image_map[media.product_id] = media.media_url

        rec_prices = db.execute(
            select(ProductSku.product_id, func.min(ProductSku.price_cent))
            .where(ProductSku.product_id.in_(rec_ids))
            .group_by(ProductSku.product_id)
        ).all()
        for product_id, min_price in rec_prices:
            rec_price_map[str(product_id)] = int(min_price or 0)

    data = {
        "id": p.id,
        "name": p.name,
        "subtitle": p.subtitle,
        "description": p.description,
        "status": p.status,
        "marketPriceCent": p.market_price_cent,
        "soldCount": p.sold_count,
        "badgePrimary": p.badge_primary,
        "badgeSecondary": p.badge_secondary,
        "mainImageUrl": medias[0].media_url if medias else "",
        "images": [m.media_url for m in medias],
        "serviceTags": ["包邮", "极速发货", "正品保障"],
        "skus": [
            {
                "id": s.id,
                "name": s.sku_name,
                "priceCent": s.price_cent,
                "priceText": _price_text(s.price_cent),
                "stock": s.stock,
            }
            for s in skus
        ],
        "recommendations": [
            {
                "id": r.id,
                "name": r.name,
                "subtitle": r.subtitle,
                "imageUrl": rec_image_map.get(r.id, ""),
                "priceCent": rec_price_map.get(r.id, 0),
            }
            for r in recommend
        ],
    }
    CACHE.set(cache_key, data, PRODUCT_DETAIL_CACHE_TTL)
    return ok(data)
