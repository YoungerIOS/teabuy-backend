from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.security import create_access_token
from app.main import app
from app.models import User

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


def _seed_user(db: Session, user_id: str, role: str) -> User:
    user = User(id=user_id, username=user_id, display_name=user_id, role=role)
    db.add(user)
    db.commit()
    return user


def _auth_header(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, 1)}"}


def test_internal_catalog_workflow():
    db = TestingSessionLocal()
    _seed_user(db, "admin_internal", "admin")
    db.close()

    create_category = client.post(
        "/api/v1/internal/catalog/categories",
        json={"id": "cat_test", "name": "测试分类", "sort": 1},
        headers=_auth_header("admin_internal"),
    )
    assert create_category.status_code == 200

    create_product = client.post(
        "/api/v1/internal/catalog/products",
        json={
            "id": "prod_test",
            "name": "测试绿茶",
            "subtitle": "联调用示例",
            "categoryId": "cat_test",
            "description": "用于前端联调的商品",
            "marketPriceCent": 19900,
            "soldCount": 3,
            "badgePrimary": "新品",
            "badgeSecondary": "测试",
            "status": "draft",
        },
        headers=_auth_header("admin_internal"),
    )
    assert create_product.status_code == 200

    put_skus = client.put(
        "/api/v1/internal/catalog/products/prod_test/skus",
        json={"items": [{"name": "250g", "priceCent": 12900, "stock": 50}]},
        headers=_auth_header("admin_internal"),
    )
    assert put_skus.status_code == 200

    put_media = client.put(
        "/api/v1/internal/catalog/products/prod_test/media",
        json={"items": [{"url": "https://example.com/p1.png", "sort": 1}]},
        headers=_auth_header("admin_internal"),
    )
    assert put_media.status_code == 200

    publish = client.patch(
        "/api/v1/internal/catalog/products/prod_test/status",
        json={"status": "active"},
        headers=_auth_header("admin_internal"),
    )
    assert publish.status_code == 200
    assert publish.json()["data"]["status"] == "active"

    detail = client.get("/api/v1/internal/catalog/products/prod_test", headers=_auth_header("admin_internal"))
    assert detail.status_code == 200
    detail_data = detail.json()["data"]
    assert len(detail_data["skus"]) == 1
    assert len(detail_data["medias"]) == 1

    public_list = client.get("/api/v1/catalog/products", params={"keyword": "测试绿茶"})
    assert public_list.status_code == 200
    items = public_list.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["id"] == "prod_test"


def test_non_admin_cannot_access_internal_catalog():
    db = TestingSessionLocal()
    _seed_user(db, "user_internal", "user")
    db.close()

    r = client.get("/api/v1/internal/catalog/categories", headers=_auth_header("user_internal"))
    assert r.status_code == 403


def test_internal_catalog_demo_seed():
    db = TestingSessionLocal()
    _seed_user(db, "admin_seed", "admin")
    db.close()

    seed = client.post("/api/v1/internal/catalog/demo-seed", headers=_auth_header("admin_seed"))
    assert seed.status_code == 200
    assert seed.json()["data"]["seededProducts"] >= 8

    categories = client.get("/api/v1/internal/catalog/categories", headers=_auth_header("admin_seed"))
    assert categories.status_code == 200
    assert len(categories.json()["data"]) >= 4

    keyword_products = client.get("/api/v1/catalog/products", params={"keyword": "碧螺春"})
    assert keyword_products.status_code == 200
    assert len(keyword_products.json()["data"]["items"]) >= 1

    resolve = client.get("/api/v1/navigation/resolve", params={"linkType": "keyword", "linkValue": "碧螺春"})
    assert resolve.status_code == 200
    assert resolve.json()["data"]["route"] == "product_list"
