from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import (
    ComparedProfessor,
    ComparisonNarrative,
    ComparisonOut,
    DimensionComparison,
    ProfessorOut,
    normalize_course_code,
)
from app.security import get_optional_user
from app.services.ai import AIService, AIUnavailable, get_ai
from app.services.matching import MIN_EVIDENCE, compatibility, user_preferences
from app.services.professors import (
    cached_ai_call,
    compute_stats,
    fingerprint,
    get_professor_or_404,
    load_reviews,
)
from app.traits import DIMENSIONS, estimate_traits

router = APIRouter(prefix="/compare", tags=["compare"])

# Trait values closer than this are reported as "similar".
SIMILARITY_MARGIN = 0.1


@router.get("", response_model=ComparisonOut)
def compare_professors(
    a: int = Query(description="First professor id"),
    b: int = Query(description="Second professor id"),
    course: str | None = Query(None, description="Restrict to reviews for this course"),
    include_ai: bool = Query(True, description="Include a Gemini-written comparison"),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
    ai: AIService = Depends(get_ai),
):
    """Side-by-side comparison for a student deciding between two professors.

    Signed-in students with preferences also get a compatibility score for each.
    """
    if a == b:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pick two different professors")
    course = normalize_course_code(course) if course else None
    prof_a, prof_b = get_professor_or_404(db, a), get_professor_or_404(db, b)
    reviews_a, reviews_b = load_reviews(db, a, course), load_reviews(db, b, course)
    traits_a, traits_b = estimate_traits(reviews_a), estimate_traits(reviews_b)
    prefs = user_preferences(user) if user else []

    def side(prof, reviews, traits) -> ComparedProfessor:
        return ComparedProfessor(
            professor=ProfessorOut.model_validate(prof),
            stats=compute_stats(reviews),
            compatibility=compatibility(prefs, traits) if prefs else None,
        )

    dimensions = []
    for key, dim in DIMENSIONS.items():
        ta, tb = traits_a[key], traits_b[key]
        if ta.evidence < MIN_EVIDENCE or tb.evidence < MIN_EVIDENCE:
            higher = "insufficient_data"
        elif abs(ta.value - tb.value) < SIMILARITY_MARGIN:
            higher = "similar"
        else:
            higher = "a" if ta.value > tb.value else "b"
        dimensions.append(
            DimensionComparison(
                dimension=key,
                label=dim.label,
                a_value=round(ta.value, 3),
                b_value=round(tb.value, 3),
                a_evidence=ta.evidence,
                b_evidence=tb.evidence,
                higher=higher,
            )
        )

    out = ComparisonOut(
        course_code=course,
        a=side(prof_a, reviews_a, traits_a),
        b=side(prof_b, reviews_b, traits_b),
        dimensions=dimensions,
    )

    if not include_ai:
        return out
    if not reviews_a or not reviews_b:
        out.narrative_note = "Both professors need reviews for an AI comparison."
        return out
    try:
        out.narrative, _ = cached_ai_call(
            db,
            key=f"compare:{a}:{b}:{course or '*'}",
            fp=fingerprint(reviews_a, reviews_b),
            schema=ComparisonNarrative,
            produce=lambda: ai.compare(
                prof_a.full_name, reviews_a, prof_b.full_name, reviews_b, course
            ),
        )
    except AIUnavailable as exc:
        out.narrative_note = str(exc)
    return out
