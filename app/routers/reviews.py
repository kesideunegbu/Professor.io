from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Review, User
from app.schemas import ReviewOut, ReviewUpdate
from app.security import get_current_user
from app.services.ai import AIService, get_ai
from app.services.professors import analyze_review

router = APIRouter(prefix="/reviews", tags=["reviews"])


def _own_review(db: Session, review_id: int, user: User) -> Review:
    review = db.get(Review, review_id)
    if review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found")
    if review.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only change your own reviews")
    return review


@router.patch("/{review_id}", response_model=ReviewOut)
def update_review(
    review_id: int,
    body: ReviewUpdate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    ai: AIService = Depends(get_ai),
):
    review = _own_review(db, review_id, user)
    changes = body.model_dump(exclude_unset=True)
    text_changed = "text" in changes and changes["text"] != review.text
    for field, value in changes.items():
        setattr(review, field, value)
    if text_changed:
        review.ai_signals = None
        review.ai_analyzed_at = None
    db.commit()
    if text_changed and ai.enabled:
        background.add_task(analyze_review, review.id, ai)
    return ReviewOut.model_validate(review).model_copy(update={"is_mine": True})


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(
    review_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    db.delete(_own_review(db, review_id, user))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
