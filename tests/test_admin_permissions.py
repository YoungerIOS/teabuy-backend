from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import Order, Refund, User, UserCredential


_test_engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    future=True,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=_test_engine, autoflush=False, autocommit=False, future=True)
client = TestClient(app)


def _auth_header(token: str) -> dict:
    return {"Authorization": token}


def _seed_user(session: Session, user_id: str, username: str, role: str) -> str:
    user = User(id=user_id, username=username, display_name=username, role=role)
    cred = UserCredential(user_id=user.id, password_hash=hash_password("password"))
    session.add_all([user, cred])
    session.flush()
    return f"Bearer {create_access_token(user.id)}"


def test_non_admin_cannot_ship_or_review_refund():
    Base.metadata.create_all(_test_engine)
    session = TestSession()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        user_token = _seed_user(session, "u1", "user1", "user")
        session.add(Order(id="o1", order_no="ON1", user_id="u1", status="PAID", total_cent=1000))
        session.add(Refund(id="r1", order_id="o1", user_id="u1", status="PENDING", amount_cent=1000))
        session.commit()

        r1 = client.post("/api/v1/orders/ON1/ship", headers=_auth_header(user_token))
        assert r1.status_code == 403

        r2 = client.post("/api/v1/refunds/r1/approve", headers=_auth_header(user_token))
        assert r2.status_code == 403
    finally:
        session.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(_test_engine)
