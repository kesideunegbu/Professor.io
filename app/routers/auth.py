from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User
from app.schemas import Token, UserCreate, UserOut, VerifyEmailIn
from app.security import create_access_token, get_current_user, hash_password, verify_password
from app.services.email import EmailSender, get_email_sender
from app.services.verification import (
    VerificationError,
    email_domain_allowed,
    issue_code,
    verification_email,
    verify_code,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _send_code(db: Session, user: User, background: BackgroundTasks, sender: EmailSender) -> None:
    try:
        code = issue_code(db, user)
    except VerificationError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc
    subject, body = verification_email(user.display_name, code)
    background.add_task(sender.send, user.email, subject, body)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    body: UserCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
):
    """Create an account and email a 6-digit verification code."""
    email = body.email.lower()
    allowed = get_settings().allowed_email_domains
    if not email_domain_allowed(email, allowed):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Please sign up with your school email ({', '.join('.' + d.lstrip('.') for d in allowed)})",
        )
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(
        email=email, password_hash=hash_password(body.password), display_name=body.display_name
    )
    db.add(user)
    db.commit()
    _send_code(db, user, background, sender)
    return user


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """OAuth2 password flow: send `username` (the email) and `password` as form fields."""
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    return Token(access_token=create_access_token(user.id))


@router.post("/verify-email", response_model=UserOut)
def verify_email(
    body: VerifyEmailIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Confirm the signed-in user's email with the code they were sent."""
    try:
        verify_code(db, user, body.code)
    except VerificationError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc
    return user


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
def resend_verification(
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
):
    """Email a new code. Limited to one request per minute."""
    _send_code(db, user, background, sender)
    return {"detail": f"A new code was sent to {user.email}"}
