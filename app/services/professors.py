import hashlib
import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import database
from app.models import AICache, Professor, Review
from app.schemas import ProfessorStats, TraitOut
from app.services.ai import PROMPT_VERSION, SIGNAL_BATCH_SIZE, AIService, AIUnavailable
from app.traits import DIMENSIONS, estimate_traits

log = logging.getLogger(__name__)


def get_professor_or_404(db: Session, professor_id: int) -> Professor:
    professor = db.get(Professor, professor_id)
    if professor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Professor not found")
    return professor


def load_reviews(db: Session, professor_id: int, course_code: str | None = None) -> list[Review]:
    query = select(Review).where(Review.professor_id == professor_id)
    if course_code:
        query = query.where(Review.course_code == course_code)
    return list(db.scalars(query.order_by(Review.created_at.desc())))


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def compute_stats(reviews: Sequence[Review]) -> ProfessorStats:
    take_again = [r.would_take_again for r in reviews if r.would_take_again is not None]
    traits = estimate_traits(reviews)
    return ProfessorStats(
        review_count=len(reviews),
        avg_quality=_avg([r.quality for r in reviews]),
        avg_difficulty=_avg([r.difficulty for r in reviews]),
        would_take_again_pct=_avg([100.0 * t for t in take_again]),
        traits=[
            TraitOut(
                dimension=k,
                label=DIMENSIONS[k].label,
                value=round(t.value, 3),
                positive=t.positive,
                negative=t.negative,
                evidence=t.evidence,
            )
            for k, t in traits.items()
        ],
    )


def fingerprint(*review_groups: Sequence[Review]) -> str:
    """Content hash of the review fields an AI output depends on."""
    h = hashlib.sha256(PROMPT_VERSION.encode())
    for group in review_groups:
        h.update(b"|")
        for r in sorted(group, key=lambda r: r.id):
            h.update(f"{r.id}:{r.course_code}:{r.quality}:{r.difficulty}:{r.text}\x00".encode())
    return h.hexdigest()


def cached_ai_call[T: BaseModel](
    db: Session,
    key: str,
    fp: str,
    schema: type[T],
    produce: Callable[[], T],
    refresh: bool = False,
) -> tuple[T, datetime]:
    """Return a cached AI result for `key` if its fingerprint still matches, else regenerate."""
    entry = db.get(AICache, key)
    if entry and entry.fingerprint == fp and not refresh:
        return schema.model_validate(entry.payload), entry.created_at
    result = produce()
    if entry is None:
        entry = AICache(key=key)
        db.add(entry)
    entry.fingerprint = fp
    entry.payload = result.model_dump()
    entry.created_at = datetime.now(UTC)
    db.commit()
    return result, entry.created_at


def analyze_review(review_id: int, ai: AIService) -> None:
    """Background task: extract teaching-style signals from a review's text with Gemini."""
    with database.SessionLocal() as db:
        review = db.get(Review, review_id)
        if review is None:
            return
        try:
            review.ai_signals = ai.extract_signals(review.text)
        except AIUnavailable as exc:
            log.warning("Could not analyze review %s: %s", review_id, exc)
            return
        review.ai_analyzed_at = datetime.now(UTC)
        db.commit()


def analyze_pending_reviews(ai: AIService, batch_size: int = SIGNAL_BATCH_SIZE) -> int:
    """Analyze every review Gemini hasn't seen yet, several per call. Returns the count analyzed."""
    analyzed = 0
    with database.SessionLocal() as db:
        while True:
            pending = list(
                db.scalars(
                    select(Review)
                    .where(Review.ai_analyzed_at.is_(None))
                    .order_by(Review.id)
                    .limit(batch_size)
                )
            )
            if not pending:
                return analyzed
            try:
                signals = ai.extract_signals_batch([r.text for r in pending])
            except AIUnavailable as exc:
                log.warning("Stopped analyzing reviews after %s: %s", analyzed, exc)
                return analyzed
            now = datetime.now(UTC)
            for review, review_signals in zip(pending, signals):
                review.ai_signals = review_signals
                review.ai_analyzed_at = now
            db.commit()
            analyzed += len(pending)
