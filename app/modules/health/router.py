from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends

from app.core.db import get_db
from app.core.response import ok

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health():
    return ok({"status": "up"})


@router.get("/db")
def health_db(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return ok({"status": "up"})
