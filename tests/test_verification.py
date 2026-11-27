from datetime import UTC, datetime, timedelta

from app import database
from app.config import get_settings
from app.models import EmailVerification
from app.services.verification import MAX_ATTEMPTS
from tests.conftest import make_professor, register


def _wrong(code: str) -> str:
    return f"{(int(code) + 1) % 10**6:06d}"


def test_register_emails_a_code_and_verifying_unlocks_reviews(client):
    headers = register(client, email="new@school.edu", verify=False)
    me = client.get("/me", headers=headers).json()
    assert me["is_verified"] is False

    to, subject, body = client.outbox.sent[-1]
    code = client.outbox.code_for("new@school.edu")
    assert to == "new@school.edu" and code in body and len(code) == 6

    blocked = client.post(
        "/professors",
        json={"first_name": "A", "last_name": "B", "department": "CS", "school": "U"},
        headers=headers,
    )
    assert blocked.status_code == 403
    assert "verify your email" in blocked.json()["detail"]

    r = client.post("/auth/verify-email", json={"code": code}, headers=headers)
    assert r.status_code == 200 and r.json()["is_verified"] is True
    make_professor(client, headers)  # now allowed
    # Verifying again is harmless; asking for another code is not needed.
    assert client.post("/auth/verify-email", json={"code": code}, headers=headers).status_code == 200
    assert client.post("/auth/resend-verification", headers=headers).status_code == 409


def test_unverified_user_can_still_browse_and_set_preferences(client):
    headers = register(client, verify=False)
    assert client.get("/professors").status_code == 200
    prefs = {"preferences": [{"dimension": "workload", "direction": "less"}]}
    assert client.put("/me/preferences", json=prefs, headers=headers).status_code == 200


def test_wrong_codes_are_limited(client):
    headers = register(client, verify=False)
    code = client.outbox.code_for("student@example.edu")

    r = client.post("/auth/verify-email", json={"code": _wrong(code)}, headers=headers)
    assert r.status_code == 400 and f"{MAX_ATTEMPTS - 1} attempts left" in r.json()["detail"]
    for _ in range(MAX_ATTEMPTS - 1):
        client.post("/auth/verify-email", json={"code": _wrong(code)}, headers=headers)
    # Even the right code is refused once attempts run out.
    r = client.post("/auth/verify-email", json={"code": code}, headers=headers)
    assert r.status_code == 400 and "Request a new code" in r.json()["detail"]
    assert client.post("/auth/verify-email", json={"code": "12ab56"}, headers=headers).status_code == 422


def test_expired_code_rejected_and_resend_has_cooldown(client):
    headers = register(client, verify=False)
    old_code = client.outbox.code_for("student@example.edu")

    r = client.post("/auth/resend-verification", headers=headers)
    assert r.status_code == 429 and "Please wait" in r.json()["detail"]

    with database.SessionLocal() as db:
        v = db.query(EmailVerification).one()
        v.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        v.sent_at = datetime.now(UTC) - timedelta(minutes=2)
        db.commit()
    r = client.post("/auth/verify-email", json={"code": old_code}, headers=headers)
    assert r.status_code == 400 and "expired" in r.json()["detail"]

    assert client.post("/auth/resend-verification", headers=headers).status_code == 202
    new_code = client.outbox.code_for("student@example.edu")
    assert len(client.outbox.sent) == 2
    r = client.post("/auth/verify-email", json={"code": new_code}, headers=headers)
    assert r.status_code == 200


def test_allowed_email_domains(client):
    settings = get_settings()
    settings.allowed_email_domains = ["edu"]
    try:
        r = client.post(
            "/auth/register",
            json={"email": "someone@gmail.com", "password": "password123", "display_name": "x"},
        )
        assert r.status_code == 400 and ".edu" in r.json()["detail"]
        ok = client.post(
            "/auth/register",
            json={"email": "someone@cs.state.edu", "password": "password123", "display_name": "x"},
        )
        assert ok.status_code == 201
    finally:
        settings.allowed_email_domains = []
