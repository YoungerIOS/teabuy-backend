from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.security import create_access_token
from app.main import app
from app.models import Category, HomeModule, Product, ProductSku, User

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def _db_env():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()


def _auth_header(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, 1)}"}


def _seed_user(db: Session, user_id: str, role: str = "user") -> User:
    user = User(id=user_id, username=user_id, display_name=user_id, role=role)
    db.add(user)
    db.commit()
    return user


def test_home_categories_default_payload():
    db = TestingSessionLocal()
    _seed_user(db, "u1")
    db.close()

    r = client.get("/api/v1/home/categories", headers=_auth_header("u1"))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["title"] == "分类"
    assert len(data["items"]) >= 5
    assert data["items"][0]["linkType"] == "category"


def test_internal_category_config_put_and_get():
    db = TestingSessionLocal()
    _seed_user(db, "admin1", role="admin")
    db.close()

    payload = {
        "title": "分类",
        "items": [
            {
                "key": "teaware",
                "name": "茶具",
                "iconUrl": "https://example.com/teaware.png",
                "linkType": "category",
                "linkValue": "teaware",
                "sort": 1,
            }
        ],
    }
    put_r = client.put("/api/v1/internal/home/category-config", json=payload, headers=_auth_header("admin1"))
    assert put_r.status_code == 200

    get_r = client.get("/api/v1/internal/home/category-config", headers=_auth_header("admin1"))
    assert get_r.status_code == 200
    data = get_r.json()["data"]
    assert data["title"] == "分类"
    assert data["items"][0]["key"] == "teaware"


def test_catalog_products_filter_and_sort():
    db = TestingSessionLocal()
    category = Category(id="c1", name="茶具", sort_order=1)
    renamed_category = Category(id="cat_tea_bag", name="袋泡茶", sort_order=2)
    db.add_all([category, renamed_category])
    p1 = Product(id="p1", name="紫砂壶", subtitle="高端茶具", category_id="c1", sold_count=10, status="active")
    p2 = Product(id="p2", name="玻璃杯", subtitle="入门茶具", category_id="c1", sold_count=99, status="active")
    p3 = Product(id="p3", name="袋泡红茶", subtitle="便携袋茶", category_id="cat_tea_bag", sold_count=8, status="active")
    db.add_all([p1, p2, p3])
    db.add_all(
        [
            ProductSku(id="s1", product_id="p1", sku_name="默认", price_cent=10000, stock=5),
            ProductSku(id="s2", product_id="p2", sku_name="默认", price_cent=2000, stock=5),
            ProductSku(id="s3", product_id="p3", sku_name="默认", price_cent=3000, stock=5),
        ]
    )
    db.commit()
    db.close()

    by_key = client.get("/api/v1/catalog/products", params={"categoryKey": "teaware"})
    assert by_key.status_code == 200
    items = by_key.json()["data"]["items"]
    assert len(items) == 2
    assert items[0]["defaultSkuId"]

    by_keyword = client.get("/api/v1/catalog/products", params={"keyword": "紫砂"})
    assert by_keyword.status_code == 200
    items = by_keyword.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["id"] == "p1"
    assert items[0]["defaultSkuId"]

    by_sort = client.get("/api/v1/catalog/products", params={"sort": "priceAsc"})
    assert by_sort.status_code == 200
    items = by_sort.json()["data"]["items"]
    assert items[0]["id"] == "p2"

    # categoryKey should still work after category name changed (ID-first resolution).
    by_category_key = client.get("/api/v1/catalog/products", params={"categoryKey": "tea_bag"})
    assert by_category_key.status_code == 200
    items = by_category_key.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["id"] == "p3"


def test_navigation_resolve():
    db = TestingSessionLocal()
    category = Category(id="cnav", name="茶具", sort_order=1)
    product = Product(id="pnav", name="测试商品", subtitle="", category_id="cnav", sold_count=1, status="active")
    db.add_all([category, product])
    db.commit()
    db.close()

    product_r = client.get("/api/v1/navigation/resolve", params={"linkType": "product", "linkValue": "pnav"})
    assert product_r.status_code == 200
    assert product_r.json()["data"]["route"] == "product_detail"

    category_r = client.get("/api/v1/navigation/resolve", params={"linkType": "category", "linkValue": "茶具"})
    assert category_r.status_code == 200
    assert category_r.json()["data"]["route"] == "product_list"

    keyword_r = client.get("/api/v1/navigation/resolve", params={"linkType": "keyword", "linkValue": "碧螺春"})
    assert keyword_r.status_code == 200
    assert keyword_r.json()["data"]["route"] == "product_list"
    assert keyword_r.json()["data"]["params"]["keyword"] == "碧螺春"


def test_home_featured_payload_fills_missing_sections():
    db = TestingSessionLocal()
    _seed_user(db, "u2")
    db.add(
        HomeModule(
            module_key="featured",
            title="精选",
            payload_json='{"tabs":[{"key":"hot","title":"热销","sort":1}],"activeTab":"hot","sections":[]}',
            sort_order=6,
            is_enabled=True,
        )
    )
    db.commit()
    db.close()

    r = client.get("/api/v1/home", headers=_auth_header("u2"))
    assert r.status_code == 200
    modules = r.json()["data"]["modules"]
    featured = next(m for m in modules if m["key"] == "featured")
    sections = featured["payload"]["sections"]
    section_keys = {s["key"] for s in sections}
    assert "tea_circle" in section_keys
    assert "boutique_recommend" in section_keys

    tea_circle = next(s for s in sections if s["key"] == "tea_circle")
    assert len(tea_circle["items"]) == 8


def test_internal_featured_config_returns_full_sections_when_empty():
    db = TestingSessionLocal()
    _seed_user(db, "admin2", role="admin")
    db.add(
        HomeModule(
            module_key="featured",
            title="精选",
            payload_json='{"tabs":[{"key":"hot","title":"热销","sort":1}],"activeTab":"hot","sections":[]}',
            sort_order=6,
            is_enabled=True,
        )
    )
    db.commit()
    db.close()

    r = client.get("/api/v1/internal/home/featured-config", headers=_auth_header("admin2"))
    assert r.status_code == 200
    data = r.json()["data"]
    section_keys = {s["key"] for s in data["sections"]}
    assert "tea_circle" in section_keys
    assert "boutique_recommend" in section_keys
