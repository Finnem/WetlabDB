"""In-process rate limiting for authentication."""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock


class LoginRateLimiter:
    """Track failed logins per IP and username within a sliding window."""

    def __init__(
        self,
        *,
        max_failures: int = 5,
        window_seconds: float = 300.0,
    ) -> None:
        self._max_failures = max_failures
        self._window = window_seconds
        self._failures: dict[tuple[str, str], list[float]] = defaultdict(list)
        self._lock = Lock()

    def _prune(self, key: tuple[str, str], now: float) -> list[float]:
        recent = [t for t in self._failures[key] if now - t <= self._window]
        self._failures[key] = recent
        return recent

    def is_blocked(self, ip: str, username: str) -> bool:
        key = (ip or "unknown", (username or "").lower())
        now = time.time()
        with self._lock:
            return len(self._prune(key, now)) >= self._max_failures

    def record_failure(self, ip: str, username: str) -> None:
        key = (ip or "unknown", (username or "").lower())
        now = time.time()
        with self._lock:
            self._prune(key, now).append(now)

    def reset(self, ip: str, username: str) -> None:
        key = (ip or "unknown", (username or "").lower())
        with self._lock:
            self._failures.pop(key, None)


login_rate_limiter = LoginRateLimiter()

__all__ = ["LoginRateLimiter", "login_rate_limiter"]
