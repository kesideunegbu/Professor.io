"""Email verification with short-lived 6-digit codes.

Codes are stored only as HMACs, expire after CODE_TTL, and allow MAX_ATTEMPTS
guesses before a new code must be requested.
"""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import EmailVerification, User

CODE_TTL = timedelta(minutes=15)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 5


class VerificationError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def email_domain_allowed(email: str, allowed_domains: list[str]) -> bool:
    if not allowed_domains:
        return True
    domain = email.rsplit("@", 1)[-1].lower()
    return any(
        domain == d.lower().lstrip(".") or domain.endswith("." + d.lower().lstrip("."))
        for d in allowed_domains
    )


def _hash(code: str) -> str:
    return hmac.new(get_settings().jwt_secret.encode(), code.encode(), hashlib.sha256).hexdigest()


def _aware(dt: datetime) -> datetime:
    # SQLite returns naive datetimes; every timestamp we store is UTC.
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def issue_code(db: Session, user: User) -> str:
    """Create a new code for the user and return it (to be emailed)."""
    v = user.verification
    if v is None:
        v = user.verification = EmailVerification()
    if v.verified_at:
        raise VerificationError(status.HTTP_409_CONFLICT, "Your email is already verified")
    now = datetime.now(UTC)
    if v.sent_at and now - _aware(v.sent_at) < RESEND_COOLDOWN:
        wait = int((RESEND_COOLDOWN - (now - _aware(v.sent_at))).total_seconds()) + 1
        raise VerificationError(
            status.HTTP_429_TOO_MANY_REQUESTS, f"Please wait {wait} seconds before requesting another code"
        )
    code = f"{secrets.randbelow(10**6):06d}"
    v.code_hash, v.expires_at, v.sent_at, v.attempts = _hash(code), now + CODE_TTL, now, 0
    db.commit()
    return code


def verify_code(db: Session, user: User, code: str) -> None:
    v = user.verification
    if v is not None and v.verified_at:
        return
    if v is None or v.code_hash is None:
        raise VerificationError(status.HTTP_400_BAD_REQUEST, "Request a verification code first")
    if v.attempts >= MAX_ATTEMPTS:
        raise VerificationError(
            status.HTTP_400_BAD_REQUEST, "Too many wrong attempts. Request a new code"
        )
    if datetime.now(UTC) > _aware(v.expires_at):
        raise VerificationError(status.HTTP_400_BAD_REQUEST, "This code has expired. Request a new one")
    if not hmac.compare_digest(_hash(code), v.code_hash):
        v.attempts += 1
        db.commit()
        left = MAX_ATTEMPTS - v.attempts
        raise VerificationError(
            status.HTTP_400_BAD_REQUEST,
            f"That code is incorrect. {left} attempt{'s' if left != 1 else ''} left"
            if left
            else "That code is incorrect. Request a new code",
        )
    v.verified_at = datetime.now(UTC)
    v.code_hash = v.expires_at = None
    db.commit()


def verification_email(name: str, code: str) -> tuple[str, str]:
    minutes = int(CODE_TTL.total_seconds() // 60)
    subject = f"Your Professor.io verification code: {code}"
    body = (
        f"Hi {name},\n\n"
        f"Your Professor.io verification code is:\n\n    {code}\n\n"
        f"It expires in {minutes} minutes. If you didn't create an account, you can ignore this email.\n"
    )
    return subject, body
