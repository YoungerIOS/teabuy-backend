from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import CheckinRecord, User, UserCredential


_test_engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    future=True,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=_test_engine, autoflush=False, autocommit=False, future=True)
client = TestClient(app)

CN_TZ = timezone(timedelta(hours=8))


def _auth_header(token: str) -> dict:
    return {"Authorization": token}


def _seed_user(session: Session, user_id: str = "u1", username: str = "u1") -> str:
    user = User(id=user_id, username=username, display_name=username, role="user", status="active")
    cred = UserCredential(user_id=user.id, password_hash=hash_password("password"))
    session.add_all([user, cred])
    session.flush()
    return f"Bearer {create_access_token(user.id)}"


def _today_cn():
    return datetime.now(CN_TZ).date()


def test_checkin_status_and_sign_flow():
    Base.metadata.create_all(_test_engine)
    session = TestSession()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        token = _seed_user(session)

        s1 = client.get("/api/v1/checkin/status", headers=_auth_header(token))
        assert s1.status_code == 200
        d1 = s1.json()["data"]
        assert d1["todaySigned"] is False
        assert d1["streakDays"] == 0
        assert len(d1["leaves"]) == 7
        assert all(item["lit"] is False for item in d1["leaves"])

        r1 = client.post("/api/v1/checkin/sign", headers=_auth_header(token))
        assert r1.status_code == 200
        d2 = r1.json()["data"]
        assert d2["idempotent"] is False
        assert d2["todaySigned"] is True
        assert d2["streakDays"] == 1
        assert d2["leaves"][0]["lit"] is True

        r2 = client.post("/api/v1/checkin/sign", headers=_auth_header(token))
        assert r2.status_code == 200
        d3 = r2.json()["data"]
        assert d3["idempotent"] is True
        assert d3["streakDays"] == 1
    finally:
        session.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(_test_engine)


def test_checkin_streak_computation_with_gap():
    Base.metadata.create_all(_test_engine)
    session = TestSession()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        token = _seed_user(session)
        today = _today_cn()

        # Consecutive records: yesterday and day-2 -> streak should be 2 before today's sign
        session.add(CheckinRecord(user_id="u1", checkin_date=today - timedelta(days=1)))
        session.add(CheckinRecord(user_id="u1", checkin_date=today - timedelta(days=2)))
        # A far record should not affect current streak
        session.add(CheckinRecord(user_id="u1", checkin_date=today - timedelta(days=5)))
        session.commit()

        s1 = client.get("/api/v1/checkin/status", headers=_auth_header(token))
        assert s1.status_code == 200
        assert s1.json()["data"]["streakDays"] == 2
        assert s1.json()["data"]["todaySigned"] is False

        sign = client.post("/api/v1/checkin/sign", headers=_auth_header(token))
        assert sign.status_code == 200
        assert sign.json()["data"]["streakDays"] == 3
        assert sign.json()["data"]["todaySigned"] is True
    finally:
        session.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(_test_engine)
