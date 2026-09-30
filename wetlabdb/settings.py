"""Process-level settings for the hosted web application.

The Tk desktop app still reads :class:`~wetlabdb.config.AppConfig` from
``mongodb_config.json``. The web server is configured from the environment
instead so Compose / systemd can inject secrets without a writable config file.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from wetlabdb.storage.local import default_local_data_dir

_log = logging.getLogger(__name__)

_WEAK_SESSION_SECRETS: frozenset[str] = frozenset(
    {"", "change-me", "change-me-in-production", "test-secret-not-for-production"}
)
_WEAK_ADMIN_PASSWORDS: frozenset[str] = frozenset(
    {"", "admin", "change-me", "change-me-in-production"}
)
_MIN_SESSION_SECRET_LEN = 32


@dataclass
class Settings:
    """Runtime settings for :func:`wetlabdb.api.create_app`."""

    mode: str = "local"
    mongo_uri: str = "mongodb://localhost:27017"
    data_dir: str = ""
    session_secret: str = "change-me"
    admin_user: str = "admin"
    admin_password: str = ""
    session_max_age: int = 60 * 60 * 24 * 7
    session_https_only: bool = False
    session_same_site: str = "lax"
    search_max_compounds: int = 50_000
    chem_wall_timeout_sec: int = 120

    def __post_init__(self) -> None:
        if not self.data_dir:
            self.data_dir = default_local_data_dir()
        self.mode = (self.mode or "local").lower()
        if self.mode not in {"local", "remote"}:
            raise ValueError(f"Unknown WETLABDB_MODE: {self.mode!r}")
        same = (self.session_same_site or "lax").lower()
        if same not in {"lax", "strict", "none"}:
            raise ValueError(f"Invalid WETLABDB_SESSION_SAME_SITE: {self.session_same_site!r}")
        self.session_same_site = same
        if self.session_max_age < 0:
            raise ValueError("WETLABDB_SESSION_MAX_AGE must be non-negative")
        if self.search_max_compounds < 1:
            raise ValueError("WETLABDB_SEARCH_MAX_COMPOUNDS must be at least 1")
        if self.chem_wall_timeout_sec < 1:
            raise ValueError("WETLABDB_CHEM_WALL_TIMEOUT_SEC must be at least 1")

    @classmethod
    def from_env(cls) -> "Settings":
        """Build from ``WETLABDB_*`` / ``MONGO_URI`` environment variables."""
        https_only = os.environ.get("WETLABDB_SESSION_HTTPS_ONLY", "").lower() in {
            "1",
            "true",
            "yes",
        }
        max_age_raw = os.environ.get("WETLABDB_SESSION_MAX_AGE", "")
        max_age = int(max_age_raw) if max_age_raw.strip() else 60 * 60 * 24 * 7
        search_max_raw = os.environ.get("WETLABDB_SEARCH_MAX_COMPOUNDS", "50000")
        chem_timeout_raw = os.environ.get("WETLABDB_CHEM_WALL_TIMEOUT_SEC", "120")
        return cls(
            mode=os.environ.get("WETLABDB_MODE", "local"),
            mongo_uri=os.environ.get("MONGO_URI", "mongodb://localhost:27017"),
            data_dir=os.environ.get("WETLABDB_DATA_DIR", "") or default_local_data_dir(),
            session_secret=os.environ.get("WETLABDB_SESSION_SECRET", "change-me"),
            admin_user=os.environ.get("WETLABDB_ADMIN_USER", "admin"),
            admin_password=os.environ.get("WETLABDB_ADMIN_PASSWORD", ""),
            session_max_age=max_age,
            session_https_only=https_only,
            session_same_site=os.environ.get("WETLABDB_SESSION_SAME_SITE", "lax"),
            search_max_compounds=int(search_max_raw),
            chem_wall_timeout_sec=int(chem_timeout_raw),
        )

    @property
    def is_local(self) -> bool:
        return self.mode == "local"

    def validate_for_runtime(self) -> None:
        """Fail closed in remote mode; warn on weak local defaults."""
        allow_insecure = os.environ.get("WETLABDB_ALLOW_INSECURE_DEV", "") == "1"
        weak_secret = (
            len(self.session_secret) < _MIN_SESSION_SECRET_LEN
            or self.session_secret in _WEAK_SESSION_SECRETS
        )
        weak_password = self.admin_password in _WEAK_ADMIN_PASSWORDS

        if self.mode == "remote" and not allow_insecure:
            if weak_secret:
                raise ValueError(
                    "WETLABDB_SESSION_SECRET must be at least "
                    f"{_MIN_SESSION_SECRET_LEN} characters and not a known default "
                    "(set WETLABDB_ALLOW_INSECURE_DEV=1 only for local debugging)."
                )
            if weak_password:
                raise ValueError(
                    "WETLABDB_ADMIN_PASSWORD must be set to a non-default value in "
                    "remote mode (set WETLABDB_ALLOW_INSECURE_DEV=1 only for local debugging)."
                )
            return

        if weak_secret:
            _log.warning(
                "Using a weak WETLABDB_SESSION_SECRET; do not deploy this configuration."
            )
        if weak_password and self.admin_password:
            _log.warning(
                "Using a weak WETLABDB_ADMIN_PASSWORD; do not deploy this configuration."
            )


__all__ = ["Settings"]
