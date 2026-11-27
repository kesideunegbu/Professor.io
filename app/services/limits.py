"""Usage limits for Gemini calls.

Two limits apply to every call: an app-wide one matching the Gemini quota, and a
per-person one so a single user can't use up everyone's share. Limits are kept in
memory, so they reset when the server restarts and are per server process.
"""

import math
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import Request

from app.config import get_settings
from app.models import User
from app.services.ai import AIUnavailable


def client_key(request: Request, user: User | None) -> str:
    """Who a call counts against: the account if signed in, otherwise the IP address."""
    if user is not None:
        return f"user:{user.id}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


class AIRateLimited(AIUnavailable):
    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.retry_after = retry_after


class RateLimiter:
    """Sliding window: at most `limit` hits per key in any `window` seconds."""

    def __init__(self, limit: int, window: float, clock: Callable[[], float] = time.monotonic):
        self.limit, self.window, self._clock = limit, window, clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def wait_time(self, key: str) -> float:
        """Seconds until `key` may make another call (0 if it may call now)."""
        hits, now = self._hits[key], self._clock()
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if not hits:
            del self._hits[key]
            return 0.0
        return 0.0 if len(hits) < self.limit else hits[0] + self.window - now

    def record(self, key: str) -> None:
        self._hits[key].append(self._clock())


class AILimits:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self.configure()

    def configure(self, per_user_per_hour: int | None = None, per_minute: int | None = None):
        settings = get_settings()
        self.per_user = RateLimiter(
            per_user_per_hour or settings.ai_requests_per_user_per_hour, 3600, self._clock
        )
        self.app_wide = RateLimiter(per_minute or settings.gemini_requests_per_minute, 60, self._clock)

    def reserve(self, client_key: str | None) -> None:
        """Count one Gemini call, or raise AIRateLimited if a limit is reached.

        Pass `client_key=None` for background work that only counts app-wide.
        """
        with self._lock:
            user_wait = self.per_user.wait_time(client_key) if client_key else 0.0
            app_wait = self.app_wide.wait_time("app")
            if user_wait:
                minutes = math.ceil(user_wait / 60)
                raise AIRateLimited(
                    "You've generated a lot of AI results recently. "
                    f"Please try again in {minutes} minute{'s' if minutes != 1 else ''}.",
                    math.ceil(user_wait),
                )
            if app_wait:
                raise AIRateLimited(
                    "The AI service is busy. Please try again in a minute.", math.ceil(app_wait)
                )
            if client_key:
                self.per_user.record(client_key)
            self.app_wide.record("app")


ai_limits = AILimits()
