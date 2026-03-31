from datetime import datetime, timedelta

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


def _seed_user(session: Session, user_id: str, username: str) -> str:
    user = User(id=user_id, username=username, display_name=username, role="user", status="active")
    cred = UserCredential(user_id=user.id, password_hash=hash_password("password"))
    session.add_all([user, cred])
    session.flush()
    return f"Bearer {create_access_token(user.id)}"


def test_notifications_contract_endpoints():
    Base.metadata.create_all(_test_engine)
    session = TestSession()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        token = _seed_user(session, "u1", "u1")
        _seed_user(session, "u2", "u2")
        now = datetime.utcnow()
        n1 = Notification(
            user_id="u1",
            title="t1",
            content="c1",
            is_read=False,
            created_at=now - timedelta(minutes=3),
            updated_at=now - timedelta(minutes=3),
            link_type="product",
            link_value="p1",
            type="system",
            priority=1,
        )
        n2 = Notification(
            user_id="u1",
            title="t2",
            content="c2",
            is_read=False,
            created_at=now - timedelta(minutes=2),
            updated_at=now - timedelta(minutes=2),
            link_type="h5",
            link_value="https://example.com",
            type="marketing",
            priority=2,
        )
        n3 = Notification(
            user_id="u1",
            title="t3",
            content="c3",
            is_read=True,
            read_at=now - timedelta(minutes=1),
            created_at=now - timedelta(minutes=1),
            updated_at=now - timedelta(minutes=1),
            type="system",
            priority=0,
        )
        n_other = Notification(user_id="u2", title="other", content="x", is_read=False)
        session.add_all([n1, n2, n3, n_other])
        session.commit()

        # summary
        s = client.get("/api/v1/notifications/summary", headers=_auth_header(token))
        assert s.status_code == 200
        assert s.json()["data"]["unreadCount"] == 2
        assert s.json()["data"]["latestNotificationAt"] is not None
        assert s.json()["data"]["serverTime"] is not None

        # list with cursor
        l1 = client.get("/api/v1/notifications?limit=2", headers=_auth_header(token))
        assert l1.status_code == 200
        d1 = l1.json()["data"]
        assert len(d1["items"]) == 2
        assert d1["unreadCount"] == 2
        assert d1["nextCursor"] != ""
        assert "linkType" in d1["items"][0]
        assert "type" in d1["items"][0]
        assert "priority" in d1["items"][0]

        l2 = client.get(f"/api/v1/notifications?limit=2&cursor={d1['nextCursor']}", headers=_auth_header(token))
        assert l2.status_code == 200
        assert len(l2.json()["data"]["items"]) == 1

        # detail
        detail_id = d1["items"][0]["id"]
        g = client.get(f"/api/v1/notifications/{detail_id}", headers=_auth_header(token))
        assert g.status_code == 200
        assert g.json()["data"]["id"] == detail_id

        # patch single read
        unread_item = next(i for i in d1["items"] if i["isRead"] is False)
        p = client.patch(f"/api/v1/notifications/{unread_item['id']}/read", json={"read": True}, headers=_auth_header(token))
        assert p.status_code == 200
        assert p.json()["data"]["unreadCount"] == 1

        # batch read
        all_list = client.get("/api/v1/notifications?limit=20", headers=_auth_header(token)).json()["data"]["items"]
        unread_ids = [it["id"] for it in all_list if not it["isRead"]]
        b = client.post("/api/v1/notifications/read-batch", json={"ids": unread_ids}, headers=_auth_header(token))
        assert b.status_code == 200
        assert b.json()["data"]["unreadCount"] == 0

        # read-all keeps contract
        ra = client.post("/api/v1/notifications/read-all", headers=_auth_header(token))
        assert ra.status_code == 200
        assert ra.json()["data"]["success"] is True
        assert ra.json()["data"]["unreadCount"] == 0
    finally:
        session.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(_test_engine)
