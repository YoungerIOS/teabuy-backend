"""
End-to-end tests for the purchase flow.
"""
import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.main import app
from app.core.config import settings
from app.models import (
    CartItem,
    Category,
    Product,
    ProductMedia,
    ProductSku,
    User,
    UserAddress,
    UserCredential,
)
from app.core.security import hash_password, create_access_token


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# StaticPool + check_same_thread=False lets the in-memory SQLite database
# be shared across threads (FastAPI TestClient runs sync endpoints in a
# thread pool but the test seeds in the main thread).
_test_engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    future=True,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestSession = sessionmaker(bind=_test_engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture(autouse=True)
def db_session():
    """Create fresh tables for every test, drop afterwards."""
    Base.metadata.create_all(_test_engine)
    session = TestSession()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db

    yield session

    session.close()
    app.dependency_overrides.clear()
    Base.metadata.drop_all(_test_engine)


client = TestClient(app)


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _seed_user(session: Session) -> tuple[User, str]:
    """Create a test user and return (user, bearer_token)."""
    user = User(id="u1", username="tester", display_name="Tester")
    cred = UserCredential(user_id=user.id, password_hash=hash_password("password"))
    session.add(user)
    session.add(cred)
    session.flush()
    token = create_access_token(user.id)
    return user, f"Bearer {token}"


def _seed_admin(session: Session) -> tuple[User, str]:
    admin = User(id="admin1", username="admin", display_name="Admin", role="admin")
    cred = UserCredential(user_id=admin.id, password_hash=hash_password("password"))
    session.add(admin)
    session.add(cred)
    session.flush()
    token = create_access_token(admin.id)
    return admin, f"Bearer {token}"


def _seed_catalog(session: Session, stock: int = 100) -> tuple[Category, Product, ProductSku]:
    """Create a category, product, and SKU."""
    cat = Category(id="cat1", name="绿茶", sort_order=1)
    prod = Product(id="prod1", name="嘉应绿茶", category_id=cat.id, description="测试商品")
    sku = ProductSku(id="sku1", product_id=prod.id, sku_name="500g装", price_cent=5000, stock=stock)
    media = ProductMedia(id="m1", product_id=prod.id, media_url="https://example.com/tea.png", sort_order=1)
    session.add_all([cat, prod, sku, media])
    session.flush()
    return cat, prod, sku


def _seed_address(session: Session, user_id: str) -> UserAddress:
    addr = UserAddress(
        id="addr1",
        user_id=user_id,
        recipient="张三",
        phone="13800138000",
        region="广东省梅州市",
        detail="梅江区xxx路123号",
        is_default=True,
    )
    session.add(addr)
    session.flush()
    return addr


def _add_to_cart(session: Session, user_id: str, sku_id: str, quantity: int = 2) -> CartItem:
    item = CartItem(id="ci1", user_id=user_id, sku_id=sku_id, quantity=quantity, selected=True)
    session.add(item)
    session.flush()
    return item


def _auth_header(token: str) -> dict:
    return {"Authorization": token}


def _callback_signature(order_no: str, callback_no: str, success: bool) -> str:
    raw = f"{order_no}:{callback_no}:{int(success)}:{settings.mock_payment_callback_secret}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestOrderCreation:
    def test_create_order_clears_cart(self, db_session):
        user, token = _seed_user(db_session)
        _seed_catalog(db_session, stock=100)
        _seed_address(db_session, user.id)
        _add_to_cart(db_session, user.id, "sku1", quantity=2)

        r = client.post(
            "/api/v1/orders",
            json={"cartItemIds": ["ci1"], "addressId": "addr1"},
            headers={**_auth_header(token), "Idempotency-Key": "key-1"},
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["idempotent"] is False

        # Cart should be empty
        cart_r = client.get("/api/v1/cart", headers=_auth_header(token))
        assert len(cart_r.json()["data"]["items"]) == 0

    def test_create_order_deducts_stock(self, db_session):
        user, token = _seed_user(db_session)
        _, _, sku = _seed_catalog(db_session, stock=50)
        _seed_address(db_session, user.id)
        _add_to_cart(db_session, user.id, "sku1", quantity=3)

        client.post(
            "/api/v1/orders",
            json={"cartItemIds": ["ci1"], "addressId": "addr1"},
            headers={**_auth_header(token), "Idempotency-Key": "key-2"},
        )

        db_session.refresh(sku)
        assert sku.stock == 47  # 50 - 3

    def test_create_order_insufficient_stock(self, db_session):
        user, token = _seed_user(db_session)
        _seed_catalog(db_session, stock=1)
        _seed_address(db_session, user.id)
        _add_to_cart(db_session, user.id, "sku1", quantity=5)

        r = client.post(
            "/api/v1/orders",
            json={"cartItemIds": ["ci1"], "addressId": "addr1"},
            headers={**_auth_header(token), "Idempotency-Key": "key-3"},
        )
        assert r.status_code == 400
        assert "insufficient stock" in r.json()["message"]

    def test_create_order_saves_product_snapshot(self, db_session):
        user, token = _seed_user(db_session)
        _seed_catalog(db_session, stock=100)
        _seed_address(db_session, user.id)
        _add_to_cart(db_session, user.id, "sku1", quantity=1)

        r = client.post(
            "/api/v1/orders",
            json={"cartItemIds": ["ci1"], "addressId": "addr1"},
            headers={**_auth_header(token), "Idempotency-Key": "key-4"},
        )
        order_no = r.json()["data"]["orderNo"]

        detail = client.get(f"/api/v1/orders/{order_no}", headers=_auth_header(token))
        items = detail.json()["data"]["items"]
        assert items[0]["productName"] == "嘉应绿茶"
        assert items[0]["skuName"] == "500g装"
        assert items[0]["imageUrl"] == "https://example.com/tea.png"

    def test_create_order_saves_address_snapshot(self, db_session):
        user, token = _seed_user(db_session)
        _seed_catalog(db_session, stock=100)
        _seed_address(db_session, user.id)
        _add_to_cart(db_session, user.id, "sku1", quantity=1)

        r = client.post(
            "/api/v1/orders",
            json={"cartItemIds": ["ci1"], "addressId": "addr1"},
            headers={**_auth_header(token), "Idempotency-Key": "key-5"},
        )
        order_no = r.json()["data"]["orderNo"]

        detail = client.get(f"/api/v1/orders/{order_no}", headers=_auth_header(token))
        addr = detail.json()["data"]["address"]
        assert addr["recipient"] == "张三"
        assert addr["phone"] == "13800138000"

    def test_create_order_invalid_address(self, db_session):
        user, token = _seed_user(db_session)
        _seed_catalog(db_session, stock=100)
        _add_to_cart(db_session, user.id, "sku1", quantity=1)

        r = client.post(
            "/api/v1/orders",
            json={"cartItemIds": ["ci1"], "addressId": "nonexistent"},
            headers={**_auth_header(token), "Idempotency-Key": "key-6"},
        )
        assert r.status_code == 400
        assert "address" in r.json()["message"]


class TestCancelOrder:
    def test_cancel_restores_stock(self, db_session):
        user, token = _seed_user(db_session)
        _, _, sku = _seed_catalog(db_session, stock=50)
        _seed_address(db_session, user.id)
        _add_to_cart(db_session, user.id, "sku1", quantity=5)

        r = client.post(
            "/api/v1/orders",
            json={"cartItemIds": ["ci1"], "addressId": "addr1"},
            headers={**_auth_header(token), "Idempotency-Key": "key-c1"},
        )
        order_no = r.json()["data"]["orderNo"]

        db_session.refresh(sku)
        assert sku.stock == 45  # 50 - 5

        client.post(f"/api/v1/orders/{order_no}/cancel", headers=_auth_header(token))

        db_session.refresh(sku)
        assert sku.stock == 50  # Restored


class TestOrderStatusFlow:
    def test_full_status_chain(self, db_session):
        user, token = _seed_user(db_session)
        _, admin_token = _seed_admin(db_session)
        _seed_catalog(db_session, stock=100)
        _seed_address(db_session, user.id)
        _add_to_cart(db_session, user.id, "sku1", quantity=1)

        r = client.post(
            "/api/v1/orders",
            json={"cartItemIds": ["ci1"], "addressId": "addr1"},
            headers={**_auth_header(token), "Idempotency-Key": "key-flow"},
        )
        order_no = r.json()["data"]["orderNo"]

        # Mock payment callback
        callback_no = "cb-flow-1"
        client.post(
            "/api/v1/payments/mock/callback",
            json={
                "orderNo": order_no,
                "callbackNo": callback_no,
                "success": True,
                "signature": _callback_signature(order_no, callback_no, True),
            },
        )

        # Check PAID
        detail = client.get(f"/api/v1/orders/{order_no}", headers=_auth_header(token))
        assert detail.json()["data"]["status"] == "PAID"

        # Ship
        r = client.post(f"/api/v1/orders/{order_no}/ship", headers=_auth_header(admin_token))
        assert r.status_code == 200

        # Confirm delivery
        r = client.post(f"/api/v1/orders/{order_no}/confirm-delivery", headers=_auth_header(token))
        assert r.status_code == 200

        detail = client.get(f"/api/v1/orders/{order_no}", headers=_auth_header(token))
        assert detail.json()["data"]["status"] == "COMPLETED"

    def test_full_status_chain_mock_ship(self, db_session):
        user, token = _seed_user(db_session)
        _seed_catalog(db_session, stock=100)
        _seed_address(db_session, user.id)
        _add_to_cart(db_session, user.id, "sku1", quantity=1)

        r = client.post(
            "/api/v1/orders",
            json={"cartItemIds": ["ci1"], "addressId": "addr1"},
            headers={**_auth_header(token), "Idempotency-Key": "key-flow-mock"},
        )
        order_no = r.json()["data"]["orderNo"]

        r = client.post(
            "/api/v1/payments/mock/pay",
            json={"orderNo": order_no, "success": True},
            headers=_auth_header(token),
        )
        assert r.status_code == 200

        detail = client.get(f"/api/v1/orders/{order_no}", headers=_auth_header(token))
        assert detail.json()["data"]["status"] == "PAID"

        r = client.post(f"/api/v1/orders/{order_no}/mock-ship", headers=_auth_header(token))
        assert r.status_code == 200

        r = client.post(f"/api/v1/orders/{order_no}/confirm-delivery", headers=_auth_header(token))
        assert r.status_code == 200

        detail = client.get(f"/api/v1/orders/{order_no}", headers=_auth_header(token))
        assert detail.json()["data"]["status"] == "COMPLETED"


class TestShippingFee:
    def test_below_threshold_charges_shipping(self, db_session):
        user, token = _seed_user(db_session)
        # SKU price 5000 cents (¥50) < ¥100 threshold
        _seed_catalog(db_session, stock=100)
        _add_to_cart(db_session, user.id, "sku1", quantity=1)

        r = client.post(
            "/api/v1/orders/preview",
            json={"cartItemIds": ["ci1"]},
            headers=_auth_header(token),
        )
        data = r.json()["data"]
        assert data["shippingCent"] == 800  # ¥8
        assert data["payableCent"] == 5800  # 5000 + 800

    def test_above_threshold_free_shipping(self, db_session):
        user, token = _seed_user(db_session)
        _seed_catalog(db_session, stock=100)
        _add_to_cart(db_session, user.id, "sku1", quantity=3)  # 5000 * 3 = 15000 > 10000

        r = client.post(
            "/api/v1/orders/preview",
            json={"cartItemIds": ["ci1"]},
            headers=_auth_header(token),
        )
        data = r.json()["data"]
        assert data["shippingCent"] == 0
        assert data["payableCent"] == 15000


class TestRefund:
    def _create_paid_order(self, db_session) -> tuple[str, str, str]:
        user, token = _seed_user(db_session)
        _, admin_token = _seed_admin(db_session)
        _seed_catalog(db_session, stock=100)
        _seed_address(db_session, user.id)
        _add_to_cart(db_session, user.id, "sku1", quantity=2)

        r = client.post(
            "/api/v1/orders",
            json={"cartItemIds": ["ci1"], "addressId": "addr1"},
            headers={**_auth_header(token), "Idempotency-Key": "key-refund"},
        )
        order_no = r.json()["data"]["orderNo"]

        callback_no = "cb-refund-1"
        client.post(
            "/api/v1/payments/mock/callback",
            json={
                "orderNo": order_no,
                "callbackNo": callback_no,
                "success": True,
                "signature": _callback_signature(order_no, callback_no, True),
            },
        )
        return order_no, token, admin_token

    def test_refund_flow(self, db_session):
        order_no, token, admin_token = self._create_paid_order(db_session)

        # Create refund
        r = client.post(
            "/api/v1/refunds",
            json={"orderNo": order_no, "reason": "不想要了"},
            headers=_auth_header(token),
        )
        assert r.status_code == 200
        refund_id = r.json()["data"]["refundId"]

        # Order should be REFUNDING
        detail = client.get(f"/api/v1/orders/{order_no}", headers=_auth_header(token))
        assert detail.json()["data"]["status"] == "REFUNDING"

        # Approve refund
        r = client.post(f"/api/v1/refunds/{refund_id}/approve", headers=_auth_header(admin_token))
        assert r.status_code == 200

        # Order should be REFUNDED
        detail = client.get(f"/api/v1/orders/{order_no}", headers=_auth_header(token))
        assert detail.json()["data"]["status"] == "REFUNDED"

    def test_refund_restores_stock(self, db_session):
        order_no, token, admin_token = self._create_paid_order(db_session)

        sku = db_session.get(ProductSku, "sku1")
        stock_after_order = sku.stock  # 100 - 2 = 98

        r = client.post(
            "/api/v1/refunds",
            json={"orderNo": order_no},
            headers=_auth_header(token),
        )
        refund_id = r.json()["data"]["refundId"]
        client.post(f"/api/v1/refunds/{refund_id}/approve", headers=_auth_header(admin_token))

        db_session.refresh(sku)
        assert sku.stock == stock_after_order + 2  # Restored

    def test_reject_refund_reverts_status(self, db_session):
        order_no, token, admin_token = self._create_paid_order(db_session)

        r = client.post(
            "/api/v1/refunds",
            json={"orderNo": order_no},
            headers=_auth_header(token),
        )
        refund_id = r.json()["data"]["refundId"]

        client.post(
            f"/api/v1/refunds/{refund_id}/reject",
            json={"reason": "invalid reason"},
            headers=_auth_header(admin_token),
        )

        detail = client.get(f"/api/v1/orders/{order_no}", headers=_auth_header(token))
        assert detail.json()["data"]["status"] == "PAID"

    def test_duplicate_refund_prevented(self, db_session):
        order_no, token, _ = self._create_paid_order(db_session)

        client.post("/api/v1/refunds", json={"orderNo": order_no}, headers=_auth_header(token))

        r = client.post("/api/v1/refunds", json={"orderNo": order_no}, headers=_auth_header(token))
        assert r.status_code == 400
        # First refund changes order to REFUNDING, so second attempt
        # is blocked by the status check (not PAID).
        assert "paid" in r.json()["message"].lower() or "pending refund" in r.json()["message"]


class TestIdempotency:
    def test_duplicate_order_returns_same(self, db_session):
        user, token = _seed_user(db_session)
        _seed_catalog(db_session, stock=100)
        _seed_address(db_session, user.id)
        _add_to_cart(db_session, user.id, "sku1", quantity=1)

        headers = {**_auth_header(token), "Idempotency-Key": "same-key"}
        r1 = client.post("/api/v1/orders", json={"cartItemIds": ["ci1"], "addressId": "addr1"}, headers=headers)
        r2 = client.post("/api/v1/orders", json={"cartItemIds": ["ci1"], "addressId": "addr1"}, headers=headers)

        assert r1.json()["data"]["orderNo"] == r2.json()["data"]["orderNo"]
        assert r2.json()["data"]["idempotent"] is True
