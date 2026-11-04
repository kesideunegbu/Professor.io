from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Professor, Review, User, UserPreference
from app.schemas import (
    PreferenceIn,
    PreferenceOption,
    PreferencesIn,
    ProfessorOut,
    Recommendation,
    UserOut,
    normalize_course_code,
)
from app.security import get_current_user
from app.services.matching import compatibility, user_preferences
from app.services.professors import compute_stats
from app.traits import DIMENSIONS, estimate_traits

router = APIRouter(tags=["users"])

_CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1, "none": 0}


@router.get("/preferences/options", response_model=list[PreferenceOption])
def preference_options():
    """Everything a student can choose during onboarding."""
    return [
        PreferenceOption(dimension=d.key, label=d.label, direction=direction, prompt=prompt)
        for d in DIMENSIONS.values()
        for direction, prompt in d.prompts.items()
    ]


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.get("/me/preferences", response_model=list[PreferenceIn])
def get_preferences(user: User = Depends(get_current_user)):
    return user.preferences


@router.put("/me/preferences", response_model=list[PreferenceIn])
def set_preferences(
    body: PreferencesIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Replace the student's preferences. Send an empty list to clear them."""
    user.preferences = [
        UserPreference(dimension=p.dimension, direction=p.direction, importance=p.importance)
        for p in body.preferences
    ]
    db.commit()
    return user.preferences


@router.get("/me/recommendations", response_model=list[Recommendation])
def recommendations(
    course: str | None = Query(None, description="Only professors with reviews for this course"),
    school: str | None = None,
    department: str | None = None,
    min_reviews: int = Query(3, ge=1),
    limit: int = Query(10, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Professors ranked by how well their reviews match the student's preferences."""
    prefs = user_preferences(user)
    if not prefs:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Set your preferences at PUT /me/preferences first"
        )

    query = select(Professor).options(selectinload(Professor.reviews))
    if course:
        query = query.where(
            Professor.reviews.any(Review.course_code == normalize_course_code(course))
        )
    if school:
        query = query.where(Professor.school.ilike(school))
    if department:
        query = query.where(Professor.department.ilike(department))

    results = []
    for professor in db.scalars(query):
        # Teaching style is a property of the professor, so traits use all their reviews.
        if len(professor.reviews) < min_reviews:
            continue
        stats = compute_stats(professor.reviews)
        results.append(
            Recommendation(
                professor=ProfessorOut.model_validate(professor),
                review_count=stats.review_count,
                avg_quality=stats.avg_quality,
                compatibility=compatibility(prefs, estimate_traits(professor.reviews)),
            )
        )

    results.sort(
        key=lambda r: (
            r.compatibility.score or 0,
            _CONFIDENCE_RANK[r.compatibility.confidence],
            r.avg_quality or 0,
        ),
        reverse=True,
    )
    return results[:limit]
