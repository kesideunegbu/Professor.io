from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "dev-only-insecure-secret-change-me-in-env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./professor_io.db"
    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_expire_minutes: int = 60 * 24
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash"
    # Usage limits for Gemini calls. Viewing saved AI results never counts.
    # The free tier allows about 5 requests per minute; raise this once billing is on.
    gemini_requests_per_minute: int = 5
    ai_requests_per_user_per_hour: int = 20
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Only allow sign-ups from these email domains, e.g. ["edu"] or ["myschool.edu"].
    # Empty means any domain is allowed.
    allowed_email_domains: list[str] = []
    # Outgoing email for verification codes. Without SMTP_HOST, emails are written
    # to the server log instead of being sent.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "Professor.io <no-reply@professor.io>"


@lru_cache
def get_settings() -> Settings:
    return Settings()
