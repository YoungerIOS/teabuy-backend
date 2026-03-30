from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import Notification, User, UserCredential


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


def _seed_user(session: Session, user_id: str, username: str, role: str = "user") -> str:
    user = User(id=user_id, username=username, display_name=username, role=role, status="active")
    cred = UserCredential(user_id=user.id, password_hash=hash_password("password"))
    session.add_all([user, cred])
    session.flush()
    return f"Bearer {create_access_token(user.id)}"


def test_internal_notification_create_broadcast_and_list():
    Base.metadata.create_all(_test_engine)
    session = TestSession()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        admin_token = _seed_user(session, "admin1", "admin1", role="admin")
        user1_token = _seed_user(session, "u1", "user1")
        _seed_user(session, "u2", "user2")
        session.commit()

        # single send
        r1 = client.post(
            "/api/v1/internal/notifications",
            json={"userId": "u1", "title": "订单提醒", "content": "您的订单已发货"},
            headers=_auth_header(admin_token),
        )
        assert r1.status_code == 200
        assert r1.json()["data"]["userId"] == "u1"

        # user can read own notifications
        r2 = client.get("/api/v1/notifications", headers=_auth_header(user1_token))
        assert r2.status_code == 200
        assert len(r2.json()["data"]["items"]) == 1

        # broadcast
        r3 = client.post(
            "/api/v1/internal/notifications/broadcast",
            json={"title": "系统公告", "content": "今晚维护窗口"},
            headers=_auth_header(admin_token),
        )
        assert r3.status_code == 200
        # active users: admin1 + u1 + u2
        assert r3.json()["data"]["sent"] == 3

        # internal list
        r4 = client.get("/api/v1/internal/notifications?userId=u1", headers=_auth_header(admin_token))
        assert r4.status_code == 200
        items = r4.json()["data"]["items"]
        assert len(items) == 2
        assert all(it["userId"] == "u1" for it in items)
    finally:
        session.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(_test_engine)


def test_internal_notification_requires_admin():
    Base.metadata.create_all(_test_engine)
    session = TestSession()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        user_token = _seed_user(session, "u1", "user1")
        session.add(Notification(user_id="u1", title="t", content="c", is_read=False))
        session.commit()

        r1 = client.get("/api/v1/internal/notifications", headers=_auth_header(user_token))
        assert r1.status_code == 403

        r2 = client.post(
            "/api/v1/internal/notifications",
            json={"userId": "u1", "title": "x", "content": "y"},
            headers=_auth_header(user_token),
        )
        assert r2.status_code == 403
    finally:
        session.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(_test_engine)
