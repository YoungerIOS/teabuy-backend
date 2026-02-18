from pydantic import BaseModel
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.response import ok
from app.models import Review, User

router = APIRouter(prefix="/reviews", tags=["review"])


class CreateReviewReq(BaseModel):
    productId: str
    rating: int = 5
    content: str = ""


@router.get("")
def list_reviews(page: int = 1, page_size: int = 20, db: Session = Depends(get_db)):
    rows = db.execute(select(Review).order_by(Review.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return ok({"page": page, "pageSize": page_size, "items": [{"id": r.id, "productId": r.product_id, "rating": r.rating, "content": r.content} for r in rows]})


@router.get("/{review_id}")
def review_detail(review_id: str, db: Session = Depends(get_db)):
    r = db.get(Review, review_id)
    if not r:
        raise ApiError(40441, "review not found", 404)
    return ok({"id": r.id, "productId": r.product_id, "rating": r.rating, "content": r.content})


@router.post("")
def create_review(req: CreateReviewReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = Review(user_id=user.id, product_id=req.productId, rating=req.rating, content=req.content)
    db.add(r)
    db.commit()
    return ok({"id": r.id})
