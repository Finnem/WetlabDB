"""Process-level settings for the hosted web application.

The Tk desktop app still reads :class:`~wetlabdb.config.AppConfig` from
``mongodb_config.json``. The web server is configured from the environment
instead so Compose / systemd can inject secrets without a writable config file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from wetlabdb.storage.local import default_local_data_dir


@dataclass
class Settings:
    """Runtime settings for :func:`wetlabdb.api.create_app`."""

    mode: str = "local"
    mongo_uri: str = "mongodb://localhost:27017"
    data_dir: str = ""
    session_secret: str = "change-me"
    admin_user: str = "admin"
    admin_password: str = ""

    def __post_init__(self) -> None:
        if not self.data_dir:
            self.data_dir = default_local_data_dir()
        self.mode = (self.mode or "local").lower()
        if self.mode not in {"local", "remote"}:
            raise ValueError(f"Unknown WETLABDB_MODE: {self.mode!r}")

    @classmethod
    def from_env(cls) -> "Settings":
        """Build from ``WETLABDB_*`` / ``MONGO_URI`` environment variables."""
        return cls(
            mode=os.environ.get("WETLABDB_MODE", "local"),
            mongo_uri=os.environ.get("MONGO_URI", "mongodb://localhost:27017"),
            data_dir=os.environ.get("WETLABDB_DATA_DIR", "") or default_local_data_dir(),
            session_secret=os.environ.get("WETLABDB_SESSION_SECRET", "change-me"),
            admin_user=os.environ.get("WETLABDB_ADMIN_USER", "admin"),
            admin_password=os.environ.get("WETLABDB_ADMIN_PASSWORD", ""),
        )

    @property
    def is_local(self) -> bool:
        return self.mode == "local"


__all__ = ["Settings"]
