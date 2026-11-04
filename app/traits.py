"""Teaching-style dimensions shared by reviews, professor profiles and student preferences.

Every dimension is a trait a professor can be "high" or "low" on (e.g. workload).
Reviews produce a signal per dimension (+1 high / -1 low) from three sources, in
increasing order of trust: Gemini's reading of the review text, the numeric
difficulty rating, and tags the student picked explicitly.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.models import Review

Direction = Literal["more", "less"]


@dataclass(frozen=True)
class Dimension:
    key: str
    label: str
    # Onboarding text for each direction a student may prefer.
    prompts: dict[str, str]
    # Plain-language description of a professor who is high / low on this trait.
    high_reason: str
    low_reason: str


DIMENSIONS: dict[str, Dimension] = {
    d.key: d
    for d in [
        Dimension(
            "clarity",
            "Clear explanations",
            {"more": "Prefer professors who explain concepts thoroughly"},
            "Students frequently praise their explanations.",
            "Students often find their explanations hard to follow.",
        ),
        Dimension(
            "workload",
            "Workload",
            {"less": "Prefer lighter workloads", "more": "Don't mind a heavy workload"},
            "Students describe the workload as heavy.",
            "Students describe the workload as manageable.",
        ),
        Dimension(
            "hands_on",
            "Hands-on assignments",
            {"more": "Prefer hands-on assignments", "less": "Prefer theory-focused courses"},
            "Assignments provide practical, hands-on experience.",
            "The course is more theory- and lecture-focused.",
        ),
        Dimension(
            "flexibility",
            "Deadline flexibility",
            {"more": "Prefer professors who are flexible with deadlines"},
            "Students say the professor is flexible with deadlines.",
            "Students report strict deadline policies.",
        ),
        Dimension(
            "challenge",
            "Challenge",
            {"more": "Prefer challenging courses", "less": "Prefer less demanding courses"},
            "Students describe the course as challenging.",
            "Students describe the course as less demanding.",
        ),
        Dimension(
            "extra_credit",
            "Extra credit",
            {"more": "Prefer professors who offer extra credit"},
            "Students mention extra-credit opportunities.",
            "Students report few or no extra-credit opportunities.",
        ),
        Dimension(
            "approachability",
            "Approachability",
            {"more": "Prefer approachable professors"},
            "Students report that the professor is approachable.",
            "Students report the professor can be hard to approach.",
        ),
    ]
}

# Tags a student can attach to a review -> (dimension, signal).
TAGS: dict[str, tuple[str, int]] = {
    "clear_explanations": ("clarity", 1),
    "confusing_lectures": ("clarity", -1),
    "heavy_workload": ("workload", 1),
    "light_workload": ("workload", -1),
    "hands_on_projects": ("hands_on", 1),
    "theory_heavy": ("hands_on", -1),
    "flexible_deadlines": ("flexibility", 1),
    "strict_deadlines": ("flexibility", -1),
    "challenging": ("challenge", 1),
    "easy_course": ("challenge", -1),
    "extra_credit": ("extra_credit", 1),
    "no_extra_credit": ("extra_credit", -1),
    "approachable": ("approachability", 1),
    "hard_to_approach": ("approachability", -1),
}

# Pseudo-reviews pulling every estimate toward 0.5, so one review can't make a trait certain.
PRIOR_WEIGHT = 2.0


@dataclass(frozen=True)
class TraitEstimate:
    value: float  # 0..1: smoothed share of mentioning reviews that describe the trait as high
    positive: int
    negative: int

    @property
    def evidence(self) -> int:
        return self.positive + self.negative


def review_signals(review: "Review") -> dict[str, int]:
    signals = {k: v for k, v in (review.ai_signals or {}).items() if k in DIMENSIONS}
    if review.difficulty >= 4:
        signals["challenge"] = 1
    elif review.difficulty <= 2:
        signals["challenge"] = -1
    for tag in review.tags or []:
        if tag in TAGS:
            dim, signal = TAGS[tag]
            signals[dim] = signal
    return signals


def estimate_traits(reviews: Iterable["Review"]) -> dict[str, TraitEstimate]:
    counts = {k: [0, 0] for k in DIMENSIONS}
    for review in reviews:
        for dim, signal in review_signals(review).items():
            counts[dim][0 if signal > 0 else 1] += 1
    return {
        k: TraitEstimate((pos + PRIOR_WEIGHT / 2) / (pos + neg + PRIOR_WEIGHT), pos, neg)
        for k, (pos, neg) in counts.items()
    }
