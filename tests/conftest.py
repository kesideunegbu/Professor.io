import os
import tempfile
from pathlib import Path

# Configure before the app (and its engine) is imported.
_DB_PATH = Path(tempfile.mkdtemp()) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH.as_posix()}"
os.environ["GEMINI_API_KEY"] = ""
os.environ["JWT_SECRET"] = "test-secret-at-least-32-bytes-long!!"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas import ComparisonNarrative, ReviewSummary  # noqa: E402
from app.services.ai import get_ai  # noqa: E402


class FakeAI:
    """Deterministic stand-in for Gemini."""

    enabled = True

    def __init__(self):
        self.calls: list[str] = []

    def summarize_reviews(self, professor_name, reviews, course_code):
        self.calls.append("summarize")
        return ReviewSummary(
            overview=f"{professor_name}: {len(reviews)} reviews",
            strengths=["Clear lectures"],
            criticisms=["Heavy homework"],
            workload="Moderate",
            grading="Fair",
            best_for="Students who like structure",
        )

    def extract_signals(self, text):
        self.calls.append("extract")
        return {"approachability": 1} if "office hours" in text.lower() else {}

    def extract_signals_batch(self, texts):
        self.calls.append("extract_batch")
        return [{"approachability": 1} if "office hours" in t.lower() else {} for t in texts]

    def compare(self, a_name, a_reviews, b_name, b_reviews, course_code):
        self.calls.append("compare")
        return ComparisonNarrative(
            overview=f"{a_name} vs {b_name}",
            key_differences=["Workload"],
            choose_a_if=["You like projects"],
            choose_b_if=["You like exams"],
        )


@pytest.fixture
def fake_ai():
    return FakeAI()


@pytest.fixture
def client(fake_ai):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    app.dependency_overrides[get_ai] = lambda: fake_ai
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def register(client, email="student@example.edu", password="password123") -> dict:
    client.post(
        "/auth/register", json={"email": email, "password": password, "display_name": "Student"}
    )
    token = client.post("/auth/login", data={"username": email, "password": password}).json()
    return {"Authorization": f"Bearer {token['access_token']}"}


def make_professor(client, headers, first="Ada", last="Lovelace", dept="CS") -> int:
    r = client.post(
        "/professors",
        json={"first_name": first, "last_name": last, "department": dept, "school": "State U"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def add_review(client, professor_id, course="CS101", n=0, **overrides) -> dict:
    """Each review comes from a new student (one review per student per course)."""
    headers = register(client, email=f"reviewer{professor_id}-{course}-{n}@example.edu")
    body = {
        "course_code": course,
        "quality": 4,
        "difficulty": 3,
        "would_take_again": True,
        "text": "A solid course with a reasonable amount of work overall.",
        "tags": [],
    } | overrides
    r = client.post(f"/professors/{professor_id}/reviews", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()
