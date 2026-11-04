"""Load sample professors and reviews for local development.

    python -m scripts.seed

If GEMINI_API_KEY is set, each review's text is also analyzed with Gemini.
"""

from app import models  # noqa: F401
from app.database import Base, SessionLocal, engine
from app.models import Professor, Review
from app.services.ai import get_ai
from app.services.professors import analyze_pending_reviews

PROFESSORS = [
    ("Maria", "Alvarez", "Computer Science", [
        (5, 2, True, ["hands_on_projects", "approachable"], "Every week we built something real. Labs were fun and she answers questions patiently in office hours."),
        (5, 3, True, ["clear_explanations", "flexible_deadlines"], "Explains recursion better than any video I've watched. Gave me an extension when I was sick."),
        (4, 2, True, ["light_workload"], "Manageable homework, project-based grading, and plenty of extra credit labs."),
        (4, 3, True, ["hands_on_projects"], "Group projects take time but you learn a ton of practical skills."),
    ]),
    ("James", "Whitfield", "Computer Science", [
        (3, 5, False, ["heavy_workload", "theory_heavy", "strict_deadlines"], "Proof-heavy lectures and weekly problem sets that take 10+ hours. No late work accepted."),
        (4, 5, True, ["challenging", "clear_explanations"], "Very hard but extremely rigorous. You will understand algorithms deeply by the end."),
        (2, 4, False, ["hard_to_approach", "no_extra_credit"], "Dismissive in office hours and exams are brutal. No curve, no extra credit."),
        (4, 4, True, ["challenging"], "If you want a challenge this is the class. Lectures are dense but well organized."),
    ]),
    ("Priya", "Natarajan", "Computer Science", [
        (5, 3, True, ["clear_explanations", "extra_credit"], "Super clear slides, and she offers extra credit for attending department talks."),
        (4, 3, True, ["approachable", "flexible_deadlines"], "Friendly and flexible. Assignments are a mix of theory and coding."),
        (4, 2, True, ["light_workload", "clear_explanations"], "Fair exams that match the lectures. Workload is very reasonable."),
    ]),
]


def main() -> None:
    Base.metadata.create_all(engine)
    ai = get_ai()
    with SessionLocal() as db:
        if db.query(Professor).count():
            print("Database already has professors; skipping seed.")
            return
        for first, last, dept, reviews in PROFESSORS:
            prof = Professor(first_name=first, last_name=last, department=dept, school="State University")
            prof.reviews = [
                Review(course_code="CS101", quality=q, difficulty=d, would_take_again=wta, tags=tags, text=text)
                for q, d, wta, tags, text in reviews
            ]
            db.add(prof)
        db.commit()
        review_count = db.query(Review).count()
    print(f"Seeded {len(PROFESSORS)} professors and {review_count} reviews.")
    if ai.enabled:
        print(f"Analyzed {analyze_pending_reviews(ai)} of {review_count} reviews with Gemini.")


if __name__ == "__main__":
    main()
