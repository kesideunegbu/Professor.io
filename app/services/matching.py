"""Professor compatibility scoring.

The score measures how closely what students *say* about a professor matches the
preferences a student set. It deliberately says nothing about grades or academic
success, and reports a confidence level based on how much evidence backs it.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.schemas import CompatibilityOut
from app.traits import DIMENSIONS, TraitEstimate

if TYPE_CHECKING:
    from app.models import User

DISCLAIMER = (
    "This score reflects how well students' descriptions of this professor match the "
    "preferences you set. It is not a prediction of your grade or academic success."
)

# Reviews mentioning a dimension needed before we cite it as a reason.
MIN_EVIDENCE = 2
# Reviews mentioning a dimension for it to count as fully covered in the confidence level.
FULL_EVIDENCE = 5
MATCH_THRESHOLD = 0.6
MISMATCH_THRESHOLD = 0.4
MAX_REASONS = 4


@dataclass(frozen=True)
class Preference:
    dimension: str
    direction: str
    importance: int


def user_preferences(user: "User") -> list[Preference]:
    return [Preference(p.dimension, p.direction, p.importance) for p in user.preferences]


def compatibility(
    preferences: Sequence[Preference], traits: dict[str, TraitEstimate]
) -> CompatibilityOut:
    if not preferences:
        return CompatibilityOut(
            score=None, confidence="none", reasons=[], concerns=[], disclaimer=DISCLAIMER
        )

    weighted = total = coverage = 0.0
    matches: list[tuple[float, str]] = []
    mismatches: list[tuple[float, str]] = []

    for pref in preferences:
        trait = traits[pref.dimension]
        alignment = trait.value if pref.direction == "more" else 1 - trait.value
        weighted += pref.importance * alignment
        total += pref.importance
        coverage += pref.importance * min(1.0, trait.evidence / FULL_EVIDENCE)

        if trait.evidence < MIN_EVIDENCE:
            continue
        dim = DIMENSIONS[pref.dimension]
        is_high = trait.value >= 0.5
        text = (
            f"{dim.high_reason if is_high else dim.low_reason} "
            f"({trait.positive if is_high else trait.negative} of {trait.evidence} "
            "reviews that mention it)"
        )
        if alignment >= MATCH_THRESHOLD:
            matches.append((pref.importance * alignment, text))
        elif alignment <= MISMATCH_THRESHOLD:
            mismatches.append((pref.importance * (1 - alignment), text))

    coverage /= total
    confidence = "high" if coverage >= 0.7 else "medium" if coverage >= 0.35 else "low"
    return CompatibilityOut(
        score=round(100 * weighted / total),
        confidence=confidence,
        reasons=[t for _, t in sorted(matches, reverse=True)[:MAX_REASONS]],
        concerns=[t for _, t in sorted(mismatches, reverse=True)[:MAX_REASONS]],
        disclaimer=DISCLAIMER,
    )
