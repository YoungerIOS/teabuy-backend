from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.response import ok
from app.models import CheckinRecord, User

router = APIRouter(prefix="/checkin", tags=["checkin"])

CN_TZ = timezone(timedelta(hours=8))


def _now_cn() -> datetime:
    return datetime.now(CN_TZ)


def _today_cn():
    return _now_cn().date()


def _recent_checkin_dates(user_id: str, db: Session, limit: int = 400):
    return db.execute(
        select(CheckinRecord.checkin_date)
        .where(CheckinRecord.user_id == user_id)
        .order_by(desc(CheckinRecord.checkin_date))
        .limit(limit)
    ).scalars().all()


def _compute_streak(user_id: str, today, db: Session) -> tuple[bool, int]:
    dates = set(_recent_checkin_dates(user_id, db, limit=400))
    today_signed = today in dates
    anchor = today if today_signed else (today - timedelta(days=1))

    streak = 0
    d = anchor
    while d in dates:
        streak += 1
        d = d - timedelta(days=1)
    return today_signed, streak


def _build_status(user_id: str, db: Session) -> dict:
    today = _today_cn()
    today_signed, streak_days = _compute_streak(user_id, today, db)
    streak_display_days = min(streak_days, 7)
    leaves = [{"day": i, "lit": i <= streak_display_days} for i in range(1, 8)]
    recent = _recent_checkin_dates(user_id, db, limit=30)
    next_checkin_at = datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=CN_TZ)

    return {
        "today": str(today),
        "todaySigned": today_signed,
        "streakDays": streak_days,
        "streakDisplayDays": streak_display_days,
        "leaves": leaves,
        "signedDates": [str(d) for d in recent],
        "nextCheckinAt": next_checkin_at.isoformat(),
        "serverTime": _now_cn().isoformat(),
    }


@router.get("/status")
def get_checkin_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(_build_status(user.id, db))


@router.post("/sign")
def sign_checkin(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = _today_cn()
    existed = db.execute(
        select(CheckinRecord).where(CheckinRecord.user_id == user.id, CheckinRecord.checkin_date == today)
    ).scalar_one_or_none()
    if existed:
        data = _build_status(user.id, db)
        data["idempotent"] = True
        return ok(data)

    db.add(CheckinRecord(user_id=user.id, checkin_date=today))
    db.commit()
    data = _build_status(user.id, db)
    data["idempotent"] = False
    return ok(data)


@router.get("/history")
def get_checkin_history(
    limit: int = Query(default=30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(CheckinRecord)
        .where(CheckinRecord.user_id == user.id)
        .order_by(desc(CheckinRecord.checkin_date))
        .limit(limit)
    ).scalars().all()
    return ok(
        {
            "items": [
                {
                    "id": r.id,
                    "date": str(r.checkin_date),
                    "createdAt": r.created_at.isoformat(),
                }
                for r in rows
            ]
        }
    )
