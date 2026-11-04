from datetime import UTC, datetime

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    preferences: Mapped[list["UserPreference"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserPreference(Base):
    """One row per preference dimension the student cares about (see app/traits.py)."""

    __tablename__ = "user_preferences"
    __table_args__ = (UniqueConstraint("user_id", "dimension"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    dimension: Mapped[str] = mapped_column(String(40))
    direction: Mapped[str] = mapped_column(String(8))  # "more" | "less"
    importance: Mapped[int]  # 1 (nice to have) .. 3 (very important)

    user: Mapped[User] = relationship(back_populates="preferences")


class Professor(Base):
    __tablename__ = "professors"
    __table_args__ = (UniqueConstraint("first_name", "last_name", "school", "department"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80), index=True)
    department: Mapped[str] = mapped_column(String(120), index=True)
    school: Mapped[str] = mapped_column(String(160), index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    reviews: Mapped[list["Review"]] = relationship(
        back_populates="professor", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class Review(Base):
    __tablename__ = "reviews"
    # One review per student per professor per course. Imported reviews have no user.
    __table_args__ = (UniqueConstraint("user_id", "professor_id", "course_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    professor_id: Mapped[int] = mapped_column(
        ForeignKey("professors.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    course_code: Mapped[str] = mapped_column(String(20), index=True)
    quality: Mapped[int]  # 1..5
    difficulty: Mapped[int]  # 1..5
    would_take_again: Mapped[bool | None]
    text: Mapped[str] = mapped_column(Text)
    # Tags the student picked explicitly (keys of app.traits.TAGS).
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Gemini-extracted {dimension: +1 | -1}; None until analyzed.
    ai_signals: Mapped[dict[str, int] | None] = mapped_column(JSON, default=None)
    ai_analyzed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    professor: Mapped[Professor] = relationship(back_populates="reviews")


class AICache(Base):
    """Cached Gemini output, invalidated when the fingerprint of its input reviews changes."""

    __tablename__ = "ai_cache"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
