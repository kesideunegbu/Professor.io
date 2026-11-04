from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Professor, Review, User
from app.schemas import (
    CompatibilityOut,
    ProfessorCreate,
    ProfessorDetail,
    ProfessorOut,
    ReviewCreate,
    ReviewOut,
    ReviewSummary,
    SummaryOut,
    normalize_course_code,
)
from app.security import get_current_user, get_optional_user
from app.services.ai import AIService, AIUnavailable, get_ai
from app.services.matching import compatibility, user_preferences
from app.services.professors import (
    analyze_review,
    cached_ai_call,
    compute_stats,
    fingerprint,
    get_professor_or_404,
    load_reviews,
)
from app.traits import estimate_traits

router = APIRouter(prefix="/professors", tags=["professors"])

MIN_REVIEWS_FOR_SUMMARY = 3


def _course(course: str | None) -> str | None:
    return normalize_course_code(course) if course else None


@router.get("", response_model=list[ProfessorOut])
def search_professors(
    q: str | None = Query(None, description="Name search"),
    school: str | None = None,
    department: str | None = None,
    course: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = select(Professor)
    if q:
        query = query.where((Professor.first_name + " " + Professor.last_name).ilike(f"%{q}%"))
    if school:
        query = query.where(Professor.school.ilike(school))
    if department:
        query = query.where(Professor.department.ilike(department))
    if course:
        query = query.where(Professor.reviews.any(Review.course_code == _course(course)))
    query = query.order_by(Professor.last_name, Professor.first_name).limit(limit).offset(offset)
    return db.scalars(query).all()


@router.post("", response_model=ProfessorOut, status_code=status.HTTP_201_CREATED)
def create_professor(
    body: ProfessorCreate, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    data = {k: v.strip() for k, v in body.model_dump().items()}
    exists = db.scalar(select(Professor).filter_by(**data))
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Professor already exists (id {exists.id})")
    professor = Professor(**data)
    db.add(professor)
    db.commit()
    return professor


@router.get("/{professor_id}", response_model=ProfessorDetail)
def get_professor(
    professor_id: int, course: str | None = None, db: Session = Depends(get_db)
):
    professor = get_professor_or_404(db, professor_id)
    stats = compute_stats(load_reviews(db, professor_id, _course(course)))
    return ProfessorDetail(**ProfessorOut.model_validate(professor).model_dump(), stats=stats)


@router.get("/{professor_id}/reviews", response_model=list[ReviewOut])
def list_reviews(
    professor_id: int,
    course: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    get_professor_or_404(db, professor_id)
    reviews = load_reviews(db, professor_id, _course(course))[offset : offset + limit]
    return [
        ReviewOut.model_validate(r).model_copy(update={"is_mine": user is not None and r.user_id == user.id})
        for r in reviews
    ]


@router.post(
    "/{professor_id}/reviews", response_model=ReviewOut, status_code=status.HTTP_201_CREATED
)
def create_review(
    professor_id: int,
    body: ReviewCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    ai: AIService = Depends(get_ai),
):
    get_professor_or_404(db, professor_id)
    duplicate = db.scalar(
        select(Review).filter_by(
            professor_id=professor_id, user_id=user.id, course_code=body.course_code
        )
    )
    if duplicate:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"You already reviewed this professor for {body.course_code} (review {duplicate.id})",
        )
    review = Review(professor_id=professor_id, user_id=user.id, **body.model_dump())
    db.add(review)
    db.commit()
    if ai.enabled:
        background.add_task(analyze_review, review.id, ai)
    return ReviewOut.model_validate(review).model_copy(update={"is_mine": True})


@router.get("/{professor_id}/summary", response_model=SummaryOut)
def review_summary(
    professor_id: int,
    course: str | None = None,
    db: Session = Depends(get_db),
    ai: AIService = Depends(get_ai),
):
    """Gemini summary of the professor's reviews. Cached until the reviews change."""
    professor = get_professor_or_404(db, professor_id)
    course = _course(course)
    reviews = load_reviews(db, professor_id, course)
    out = SummaryOut(
        professor_id=professor_id,
        course_code=course,
        review_count=len(reviews),
        summary=None,
        generated_at=None,
    )
    if len(reviews) < MIN_REVIEWS_FOR_SUMMARY:
        out.note = f"At least {MIN_REVIEWS_FOR_SUMMARY} reviews are needed for a summary."
        return out
    try:
        out.summary, out.generated_at = cached_ai_call(
            db,
            key=f"summary:{professor_id}:{course or '*'}",
            fp=fingerprint(reviews),
            schema=ReviewSummary,
            produce=lambda: ai.summarize_reviews(professor.full_name, reviews, course),
        )
    except AIUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return out


@router.get("/{professor_id}/compatibility", response_model=CompatibilityOut)
def professor_compatibility(
    professor_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    get_professor_or_404(db, professor_id)
    traits = estimate_traits(load_reviews(db, professor_id))
    return compatibility(user_preferences(user), traits)
