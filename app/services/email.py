"""Outgoing email. Uses SMTP when configured, otherwise logs the message (for local dev)."""

import logging
import smtplib
from email.message import EmailMessage
from functools import lru_cache
from typing import Protocol

from app.config import get_settings

log = logging.getLogger(__name__)


class EmailSender(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class SmtpEmailSender:
    def __init__(self, host: str, port: int, username: str | None, password: str | None, sender: str):
        self._host, self._port = host, port
        self._username, self._password = username, password
        self._sender = sender

    def send(self, to, subject, body):
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = self._sender, to, subject
        message.set_content(body)
        try:
            # Port 465 uses TLS from the start; other ports (usually 587) upgrade with STARTTLS.
            if self._port == 465:
                smtp = smtplib.SMTP_SSL(self._host, self._port, timeout=20)
            else:
                smtp = smtplib.SMTP(self._host, self._port, timeout=20)
                smtp.starttls()
            with smtp:
                if self._username:
                    smtp.login(self._username, self._password or "")
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            # Runs as a background task, so log rather than raise; the user can resend.
            log.error("Could not send email to %s: %s", to, exc)


class ConsoleEmailSender:
    def send(self, to, subject, body):
        log.warning("SMTP is not configured; email not sent.\nTo: %s\nSubject: %s\n\n%s", to, subject, body)


@lru_cache
def get_email_sender() -> EmailSender:
    s = get_settings()
    if not s.smtp_host:
        return ConsoleEmailSender()
    return SmtpEmailSender(s.smtp_host, s.smtp_port, s.smtp_username, s.smtp_password, s.smtp_from)
