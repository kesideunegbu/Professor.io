from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.traits import DIMENSIONS, TAGS

ORM = ConfigDict(from_attributes=True)


def normalize_course_code(code: str) -> str:
    return "".join(code.split()).upper()


# --- auth / users ---------------------------------------------------------


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)


class UserOut(BaseModel):
    model_config = ORM
    id: int
    email: EmailStr
    display_name: str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --- preferences ----------------------------------------------------------


class PreferenceIn(BaseModel):
    model_config = ORM
    dimension: str
    direction: Literal["more", "less"]
    importance: int = Field(2, ge=1, le=3)

    @model_validator(mode="after")
    def _check_dimension(self) -> "PreferenceIn":
        dim = DIMENSIONS.get(self.dimension)
        if dim is None:
            raise ValueError(f"Unknown dimension {self.dimension!r}")
        if self.direction not in dim.prompts:
            raise ValueError(f"Direction {self.direction!r} is not offered for {self.dimension!r}")
        return self


class PreferencesIn(BaseModel):
    preferences: list[PreferenceIn] = Field(max_length=len(DIMENSIONS))

    @field_validator("preferences")
    @classmethod
    def _unique(cls, prefs: list[PreferenceIn]) -> list[PreferenceIn]:
        if len({p.dimension for p in prefs}) != len(prefs):
            raise ValueError("Each dimension may appear only once")
        return prefs


class PreferenceOption(BaseModel):
    dimension: str
    label: str
    direction: Literal["more", "less"]
    prompt: str


# --- professors -----------------------------------------------------------


class ProfessorCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    department: str = Field(min_length=1, max_length=120)
    school: str = Field(min_length=1, max_length=160)


class ProfessorOut(BaseModel):
    model_config = ORM
    id: int
    first_name: str
    last_name: str
    department: str
    school: str


class TraitOut(BaseModel):
    dimension: str
    label: str
    value: float = Field(description="0..1, how strongly reviews describe this trait as high")
    positive: int
    negative: int
    evidence: int


class ProfessorStats(BaseModel):
    review_count: int
    avg_quality: float | None
    avg_difficulty: float | None
    would_take_again_pct: float | None
    traits: list[TraitOut]


class ProfessorDetail(ProfessorOut):
    stats: ProfessorStats


# --- reviews --------------------------------------------------------------


def _validate_tags(tags: list[str] | None) -> list[str] | None:
    if tags is None:
        return None
    unknown = set(tags) - TAGS.keys()
    if unknown:
        raise ValueError(f"Unknown tags: {sorted(unknown)}")
    dims = [TAGS[t][0] for t in set(tags)]
    if len(dims) != len(set(dims)):
        raise ValueError("Tags contradict each other (same dimension tagged twice)")
    return sorted(set(tags))


class ReviewBase(BaseModel):
    quality: int = Field(ge=1, le=5)
    difficulty: int = Field(ge=1, le=5)
    would_take_again: bool | None = None
    text: str = Field(min_length=20, max_length=3000)
    tags: list[str] = Field(default_factory=list, max_length=8)

    _check_tags = field_validator("tags")(_validate_tags)


class ReviewCreate(ReviewBase):
    course_code: str = Field(min_length=2, max_length=20)

    @field_validator("course_code")
    @classmethod
    def _normalize(cls, code: str) -> str:
        return normalize_course_code(code)


class ReviewUpdate(BaseModel):
    quality: int | None = Field(None, ge=1, le=5)
    difficulty: int | None = Field(None, ge=1, le=5)
    would_take_again: bool | None = None
    text: str | None = Field(None, min_length=20, max_length=3000)
    tags: list[str] | None = Field(None, max_length=8)

    _check_tags = field_validator("tags")(_validate_tags)


class ReviewOut(BaseModel):
    model_config = ORM
    id: int
    professor_id: int
    course_code: str
    quality: int
    difficulty: int
    would_take_again: bool | None
    text: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    is_mine: bool = False


# --- AI summaries ---------------------------------------------------------


class ReviewSummary(BaseModel):
    overview: str
    strengths: list[str]
    criticisms: list[str]
    workload: str
    grading: str
    best_for: str


class SummaryOut(BaseModel):
    professor_id: int
    course_code: str | None
    review_count: int
    summary: ReviewSummary | None
    generated_at: datetime | None
    note: str | None = None


# --- compatibility / recommendations --------------------------------------


class CompatibilityOut(BaseModel):
    score: int | None = Field(description="0-100 alignment with your stated preferences")
    confidence: Literal["none", "low", "medium", "high"]
    reasons: list[str]
    concerns: list[str]
    disclaimer: str


class Recommendation(BaseModel):
    professor: ProfessorOut
    review_count: int
    avg_quality: float | None
    compatibility: CompatibilityOut


# --- comparison -----------------------------------------------------------


class ComparisonNarrative(BaseModel):
    overview: str
    key_differences: list[str]
    choose_a_if: list[str]
    choose_b_if: list[str]


class DimensionComparison(BaseModel):
    dimension: str
    label: str
    a_value: float
    b_value: float
    a_evidence: int
    b_evidence: int
    higher: Literal["a", "b", "similar", "insufficient_data"]


class ComparedProfessor(BaseModel):
    professor: ProfessorOut
    stats: ProfessorStats
    compatibility: CompatibilityOut | None = None


class ComparisonOut(BaseModel):
    course_code: str | None
    a: ComparedProfessor
    b: ComparedProfessor
    dimensions: list[DimensionComparison]
    narrative: ComparisonNarrative | None = None
    narrative_note: str | None = None
