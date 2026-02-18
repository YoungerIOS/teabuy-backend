from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


if not settings.db_url:
    # allow app import for local no-db mode; db endpoints will fail with clear error
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
else:
    engine = create_engine(settings.db_url, future=True, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
