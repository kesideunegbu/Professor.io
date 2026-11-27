from app import database
from app.models import Review
from app.services.limits import RateLimiter
from app.services.professors import analyze_pending_reviews
from tests.conftest import add_review, make_professor, register


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _professor_with_reviews(client, headers, last, n=3):
    pid = make_professor(client, headers, last=last)
    for i in range(n):
        add_review(client, pid, n=i)
    return pid


def test_rate_limiter_sliding_window():
    clock = FakeClock()
    limiter = RateLimiter(limit=2, window=60, clock=clock)
    assert limiter.wait_time("x") == 0
    limiter.record("x")
    clock.now += 10
    limiter.record("x")
    assert limiter.wait_time("x") == 50  # oldest hit leaves the window in 50s
    assert limiter.wait_time("someone-else") == 0
    clock.now += 50
    assert limiter.wait_time("x") == 0


def test_per_user_limit_counts_only_new_summaries(client, fake_ai, generous_ai_limits):
    headers = register(client)
    a = _professor_with_reviews(client, headers, "Alpha")
    b = _professor_with_reviews(client, headers, "Beta")
    generous_ai_limits.configure(per_user_per_hour=1, per_minute=1000)

    assert client.get(f"/professors/{a}/summary").status_code == 200
    # Viewing the saved summary again is free.
    assert client.get(f"/professors/{a}/summary").status_code == 200
    r = client.get(f"/professors/{b}/summary")
    assert r.status_code == 429
    assert "try again in 60 minutes" in r.json()["detail"]
    assert int(r.headers["Retry-After"]) > 3500
    assert fake_ai.calls.count("summarize") == 1

    # A signed-in user has their own allowance, separate from anonymous visitors.
    assert client.get(f"/professors/{b}/summary", headers=headers).status_code == 200


def test_app_wide_limit_says_busy(client, generous_ai_limits):
    headers = register(client)
    a = _professor_with_reviews(client, headers, "Alpha")
    b = _professor_with_reviews(client, headers, "Beta")
    generous_ai_limits.configure(per_user_per_hour=1000, per_minute=1)

    assert client.get(f"/professors/{a}/summary").status_code == 200
    r = client.get(f"/professors/{b}/summary", headers=headers)
    assert r.status_code == 429 and "busy" in r.json()["detail"]
    assert int(r.headers["Retry-After"]) <= 60


def test_compare_shows_limit_as_a_note(client, generous_ai_limits):
    headers = register(client)
    a = _professor_with_reviews(client, headers, "Alpha")
    b = _professor_with_reviews(client, headers, "Beta")
    generous_ai_limits.configure(per_user_per_hour=1, per_minute=1000)

    client.get(f"/professors/{a}/summary")
    r = client.get("/compare", params={"a": a, "b": b})
    assert r.status_code == 200
    assert r.json()["narrative"] is None
    assert "try again" in r.json()["narrative_note"]
    assert r.json()["a"]["stats"]["review_count"] == 3  # the rest still works


def test_review_analysis_is_skipped_when_busy_and_caught_up_later(client, fake_ai, generous_ai_limits):
    headers = register(client)
    pid = make_professor(client, headers)
    generous_ai_limits.configure(per_user_per_hour=1000, per_minute=1)
    add_review(client, pid, n=1)
    add_review(client, pid, n=2)  # app-wide limit reached: analysis skipped
    with database.SessionLocal() as db:
        assert db.query(Review).filter(Review.ai_analyzed_at.is_(None)).count() == 1

    generous_ai_limits.configure(per_user_per_hour=1000, per_minute=1000)
    assert analyze_pending_reviews(fake_ai) == 1


def test_disabled_ai_never_counts(client, generous_ai_limits):
    from app.main import app
    from app.services.ai import DisabledAI, get_ai

    headers = register(client)
    pid = _professor_with_reviews(client, headers, "Alpha")
    app.dependency_overrides[get_ai] = DisabledAI
    generous_ai_limits.configure(per_user_per_hour=1, per_minute=1)
    for _ in range(3):
        r = client.get(f"/professors/{pid}/summary")
        assert r.status_code == 503 and "GEMINI_API_KEY" in r.json()["detail"]
