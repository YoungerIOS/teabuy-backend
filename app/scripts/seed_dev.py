import json
from datetime import datetime

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import (
    Category,
    HomeModule,
    Product,
    ProductMedia,
    ProductSku,
    User,
    UserAddress,
    UserCredential,
    UserSession,
)


def upsert_user(db, username: str, password: str, role: str) -> User:
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if not user:
        user = User(username=username, display_name=username, role=role)
        db.add(user)
        db.flush()
        db.add(UserCredential(user_id=user.id, password_hash=hash_password(password)))
        db.add(UserSession(user_id=user.id, refresh_version=1, updated_at=datetime.utcnow()))
    else:
        user.role = role
    return user


def upsert_category(db, name: str, sort_order: int) -> Category:
    cat = db.execute(select(Category).where(Category.name == name)).scalar_one_or_none()
    if not cat:
        cat = Category(name=name, sort_order=sort_order)
        db.add(cat)
        db.flush()
    return cat


def upsert_product(
    db,
    category: Category,
    name: str,
    subtitle: str,
    description: str,
    market_price_cent: int,
    sold_count: int,
    badge_primary: str,
    badge_secondary: str,
    image_url: str,
    sku_name: str,
    price_cent: int,
    stock: int,
) -> Product:
    p = db.execute(select(Product).where(Product.name == name, Product.category_id == category.id)).scalar_one_or_none()
    if not p:
        p = Product(
            category_id=category.id,
            name=name,
            subtitle=subtitle,
            description=description,
            market_price_cent=market_price_cent,
            sold_count=sold_count,
            badge_primary=badge_primary,
            badge_secondary=badge_secondary,
            status="active",
        )
        db.add(p)
        db.flush()
    else:
        p.subtitle = subtitle
        p.description = description
        p.market_price_cent = market_price_cent
        p.sold_count = sold_count
        p.badge_primary = badge_primary
        p.badge_secondary = badge_secondary
        p.status = "active"

    media = db.execute(select(ProductMedia).where(ProductMedia.product_id == p.id)).scalars().first()
    if not media:
        media = ProductMedia(product_id=p.id, media_url=image_url, sort_order=1)
        db.add(media)
    else:
        media.media_url = image_url

    sku = db.execute(select(ProductSku).where(ProductSku.product_id == p.id)).scalars().first()
    if not sku:
        sku = ProductSku(product_id=p.id, sku_name=sku_name, price_cent=price_cent, stock=stock)
        db.add(sku)
    else:
        sku.sku_name = sku_name
        sku.price_cent = price_cent
        sku.stock = stock
    return p


def upsert_home_module(db, module_key: str, title: str, payload: dict, sort_order: int):
    m = db.execute(select(HomeModule).where(HomeModule.module_key == module_key)).scalars().first()
    if not m:
        m = HomeModule(
            module_key=module_key,
            title=title,
            payload_json=json.dumps(payload, ensure_ascii=False),
            sort_order=sort_order,
            is_enabled=True,
        )
        db.add(m)
    else:
        m.title = title
        m.payload_json = json.dumps(payload, ensure_ascii=False)
        m.sort_order = sort_order
        m.is_enabled = True


def run() -> None:
    db = SessionLocal()
    try:
        admin = upsert_user(db, "admin", "Admin123456", "admin")
        user = upsert_user(db, "test001", "12345678", "user")
        upsert_user(db, "test002", "12345678", "user")

        cat_green = upsert_category(db, "绿茶", 1)
        cat_black = upsert_category(db, "红茶", 2)

        upsert_product(
            db,
            cat_green,
            "嘉应银针绿茶",
            "清香回甘",
            "高山采摘银针绿茶，口感鲜爽",
            6800,
            1200,
            "新品",
            "包邮",
            "https://nfzznasyztaontqmuhjq.supabase.co/storage/v1/object/public/product-images/home/home_review_bg_3.png",
            "250g/盒",
            5800,
            200,
        )
        upsert_product(
            db,
            cat_black,
            "客家红茶",
            "醇厚回甘",
            "客家工艺红茶，茶香浓郁",
            5200,
            860,
            "热销",
            "次日达",
            "https://nfzznasyztaontqmuhjq.supabase.co/storage/v1/object/public/product-images/home/home_review_bg_1.png",
            "250g/盒",
            4600,
            260,
        )

        addr = db.execute(select(UserAddress).where(UserAddress.user_id == user.id, UserAddress.is_default == True)).scalars().first()
        if not addr:
            db.add(
                UserAddress(
                    user_id=user.id,
                    recipient="张三",
                    phone="13800138000",
                    region="广东省梅州市",
                    detail="梅江区嘉应学院",
                    is_default=True,
                )
            )

        updated = int(datetime.utcnow().timestamp())
        upsert_home_module(
            db,
            "review",
            "茶评",
            {
                "topics": [
                    {
                        "title": "绿茶",
                        "imageUrl": "https://nfzznasyztaontqmuhjq.supabase.co/storage/v1/object/public/product-images/home/home_review_bg_3.png",
                        "sort": 1,
                    }
                ],
                "updatedAt": updated,
            },
            3,
        )
        upsert_home_module(
            db,
            "new_tea",
            "新茶上市",
            {
                "notice": "限量好茶免费品，品出慢时光",
                "items": [
                    {
                        "title": "嘉应银针绿茶",
                        "subtitle": "春茶首发",
                        "imageUrl": "https://nfzznasyztaontqmuhjq.supabase.co/storage/v1/object/public/product-images/home/home_new_tea_1.png",
                        "wantsText": "100人想试",
                        "sort": 1,
                    }
                ],
                "updatedAt": updated,
            },
            4,
        )
        upsert_home_module(
            db,
            "featured",
            "精选",
            {
                "tabs": [{"key": "recommend", "title": "推荐", "sort": 1}],
                "activeTab": "recommend",
                "sections": [],
                "updatedAt": updated,
            },
            6,
        )

        db.commit()
        print(f"seed done: admin={admin.username}, user={user.username}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
