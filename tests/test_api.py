from tests.conftest import add_review, make_professor, register


def test_register_login_and_me(client):
    headers = register(client)
    r = client.get("/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["email"] == "student@example.edu"
    assert client.post("/auth/login", data={"username": "student@example.edu", "password": "nope"}).status_code == 401
    assert client.get("/me").status_code == 401


def test_duplicate_registration_rejected(client):
    register(client)
    r = client.post(
        "/auth/register",
        json={"email": "STUDENT@example.edu", "password": "password123", "display_name": "x"},
    )
    assert r.status_code == 409


def test_review_lifecycle_and_stats(client, fake_ai):
    headers = register(client)
    pid = make_professor(client, headers)
    r = client.post(
        f"/professors/{pid}/reviews",
        json={
            "course_code": "cs 101",
            "quality": 5,
            "difficulty": 4,
            "would_take_again": True,
            "text": "Great lectures and always available in office hours.",
            "tags": ["clear_explanations"],
        },
        headers=headers,
    )
    assert r.status_code == 201
    review = r.json()
    assert review["course_code"] == "CS101"
    assert review["is_mine"] is True
    assert "extract" in fake_ai.calls  # background analysis ran

    # One review per student per course.
    dup = client.post(
        f"/professors/{pid}/reviews",
        json={"course_code": "CS101", "quality": 1, "difficulty": 1, "text": "x" * 25},
        headers=headers,
    )
    assert dup.status_code == 409

    stats = client.get(f"/professors/{pid}").json()["stats"]
    traits = {t["dimension"]: t for t in stats["traits"]}
    assert stats["review_count"] == 1
    assert stats["avg_quality"] == 5
    assert traits["clarity"]["positive"] == 1  # from tag
    assert traits["challenge"]["positive"] == 1  # from difficulty 4
    assert traits["approachability"]["positive"] == 1  # from AI signal

    other = register(client, email="other@example.edu")
    assert client.patch(f"/reviews/{review['id']}", json={"quality": 1}, headers=other).status_code == 403
    r = client.patch(f"/reviews/{review['id']}", json={"quality": 3}, headers=headers)
    assert r.json()["quality"] == 3
    assert client.delete(f"/reviews/{review['id']}", headers=headers).status_code == 204
    assert client.get(f"/professors/{pid}").json()["stats"]["review_count"] == 0


def test_contradictory_tags_rejected(client):
    headers = register(client)
    pid = make_professor(client, headers)
    r = client.post(
        f"/professors/{pid}/reviews",
        json={
            "course_code": "CS101",
            "quality": 3,
            "difficulty": 3,
            "text": "Mixed feelings about this course overall.",
            "tags": ["heavy_workload", "light_workload"],
        },
        headers=headers,
    )
    assert r.status_code == 422


def test_search(client):
    headers = register(client)
    pid = make_professor(client, headers)
    make_professor(client, headers, first="Alan", last="Turing", dept="Math")
    add_review(client, pid, course="CS201")
    assert [p["last_name"] for p in client.get("/professors", params={"q": "ada love"}).json()] == ["Lovelace"]
    assert len(client.get("/professors", params={"department": "math"}).json()) == 1
    assert [p["id"] for p in client.get("/professors", params={"course": "cs 201"}).json()] == [pid]


def test_summary_is_cached_until_reviews_change(client, fake_ai):
    headers = register(client)
    pid = make_professor(client, headers)
    add_review(client, pid, n=1)
    r = client.get(f"/professors/{pid}/summary").json()
    assert r["summary"] is None and "At least" in r["note"]

    add_review(client, pid, n=2)
    add_review(client, pid, n=3)
    first = client.get(f"/professors/{pid}/summary").json()
    assert first["summary"]["overview"] == "Ada Lovelace: 3 reviews"
    client.get(f"/professors/{pid}/summary")
    assert fake_ai.calls.count("summarize") == 1

    add_review(client, pid, n=4)
    assert client.get(f"/professors/{pid}/summary").json()["summary"]["overview"].endswith("4 reviews")
    assert fake_ai.calls.count("summarize") == 2


def test_summary_returns_503_when_ai_disabled(client):
    from app.main import app
    from app.services.ai import DisabledAI, get_ai

    headers = register(client)
    pid = make_professor(client, headers)
    for n in range(3):
        add_review(client, pid, n=n)
    app.dependency_overrides[get_ai] = DisabledAI
    r = client.get(f"/professors/{pid}/summary")
    assert r.status_code == 503
    assert "GEMINI_API_KEY" in r.json()["detail"]


def test_preferences_validation(client):
    headers = register(client)
    options = client.get("/preferences/options").json()
    assert {"dimension": "workload", "label": "Workload", "direction": "less", "prompt": "Prefer lighter workloads"} in options

    bad_direction = {"preferences": [{"dimension": "clarity", "direction": "less", "importance": 2}]}
    assert client.put("/me/preferences", json=bad_direction, headers=headers).status_code == 422
    unknown = {"preferences": [{"dimension": "vibes", "direction": "more"}]}
    assert client.put("/me/preferences", json=unknown, headers=headers).status_code == 422

    good = {"preferences": [{"dimension": "workload", "direction": "less", "importance": 3}]}
    assert client.put("/me/preferences", json=good, headers=headers).status_code == 200
    assert client.get("/me/preferences", headers=headers).json() == good["preferences"]


def test_recommendations_rank_by_preference_fit(client):
    headers = register(client)
    hands_on = make_professor(client, headers, first="Grace", last="Hopper")
    lecture = make_professor(client, headers, first="Edsger", last="Dijkstra")
    for n in range(5):
        add_review(client, hands_on, n=n, difficulty=2, tags=["hands_on_projects", "clear_explanations", "light_workload"])
        add_review(client, lecture, n=n, difficulty=5, tags=["theory_heavy", "heavy_workload"])

    assert client.get("/me/recommendations", headers=headers).status_code == 400

    prefs = {
        "preferences": [
            {"dimension": "hands_on", "direction": "more", "importance": 3},
            {"dimension": "workload", "direction": "less", "importance": 2},
            {"dimension": "clarity", "direction": "more", "importance": 2},
        ]
    }
    client.put("/me/preferences", json=prefs, headers=headers)
    recs = client.get("/me/recommendations", params={"course": "CS101"}, headers=headers).json()

    assert [r["professor"]["id"] for r in recs] == [hands_on, lecture]
    top, bottom = recs[0]["compatibility"], recs[1]["compatibility"]
    assert top["score"] > 75 > 25 > bottom["score"]
    assert top["confidence"] == "high"
    assert any("hands-on" in reason for reason in top["reasons"])
    assert any("workload as heavy" in c for c in bottom["concerns"])
    assert "not a prediction" in top["disclaimer"]

    single = client.get(f"/professors/{hands_on}/compatibility", headers=headers).json()
    assert single["score"] == top["score"]


def test_compatibility_without_evidence_is_neutral_and_low_confidence(client):
    headers = register(client)
    pid = make_professor(client, headers)
    add_review(client, pid)
    client.put(
        "/me/preferences",
        json={"preferences": [{"dimension": "extra_credit", "direction": "more"}]},
        headers=headers,
    )
    c = client.get(f"/professors/{pid}/compatibility", headers=headers).json()
    assert c["score"] == 50
    assert c["confidence"] == "low"
    assert c["reasons"] == [] and c["concerns"] == []


def test_compare(client, fake_ai):
    headers = register(client)
    a = make_professor(client, headers, first="Grace", last="Hopper")
    b = make_professor(client, headers, first="Edsger", last="Dijkstra")
    for n in range(3):
        add_review(client, a, n=n, quality=5, difficulty=2, tags=["light_workload"])
        add_review(client, b, n=n, quality=3, difficulty=5, tags=["heavy_workload"])
    add_review(client, b, course="CS999", n=9, quality=1)

    assert client.get("/compare", params={"a": a, "b": a}).status_code == 400
    assert client.get("/compare", params={"a": a, "b": 999}).status_code == 404

    r = client.get("/compare", params={"a": a, "b": b, "course": "cs101"}).json()
    assert r["a"]["stats"]["avg_quality"] == 5
    assert r["b"]["stats"]["review_count"] == 3  # CS999 review excluded
    assert r["a"]["compatibility"] is None  # anonymous
    dims = {d["dimension"]: d for d in r["dimensions"]}
    assert dims["workload"]["higher"] == "b"
    assert dims["challenge"]["higher"] == "b"
    assert dims["extra_credit"]["higher"] == "insufficient_data"
    assert r["narrative"]["overview"] == "Grace Hopper vs Edsger Dijkstra"

    client.get("/compare", params={"a": a, "b": b, "course": "cs101"})
    assert fake_ai.calls.count("compare") == 1

    client.put(
        "/me/preferences",
        json={"preferences": [{"dimension": "workload", "direction": "less", "importance": 3}]},
        headers=headers,
    )
    r = client.get("/compare", params={"a": a, "b": b, "include_ai": False}, headers=headers).json()
    assert r["narrative"] is None
    assert r["a"]["compatibility"]["score"] > r["b"]["compatibility"]["score"]


def test_analyze_pending_reviews_batches_calls(client, fake_ai):
    from app import database
    from app.models import Review
    from app.services.professors import analyze_pending_reviews

    headers = register(client)
    pid = make_professor(client, headers)
    for n in range(5):
        add_review(client, pid, n=n, text=f"Review {n}: helpful in office hours every week.")
    with database.SessionLocal() as db:  # pretend the per-review background analysis never ran
        db.query(Review).update({Review.ai_signals: None, Review.ai_analyzed_at: None})
        db.commit()

    assert analyze_pending_reviews(fake_ai, batch_size=2) == 5
    assert fake_ai.calls.count("extract_batch") == 3
    assert analyze_pending_reviews(fake_ai) == 0
    traits = {t["dimension"]: t for t in client.get(f"/professors/{pid}").json()["stats"]["traits"]}
    assert traits["approachability"]["positive"] == 5
