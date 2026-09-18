"""Persistent application configuration.

The original ``MongoBrowser`` kept settings in an ad-hoc dictionary that was
flushed to ``mongodb_config.json`` by hand. ``AppConfig`` replaces that with a
typed :class:`dataclasses.dataclass` while keeping the on-disk format
backwards-compatible (additive keys only, unknown keys are preserved).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from typing import Any

from wetlabdb.storage import PYMONGO_AVAILABLE, default_local_data_dir


CONFIG_FILENAME = "mongodb_config.json"


def _default_mode() -> str:
    return "remote" if PYMONGO_AVAILABLE else "local"


@dataclass
class AppConfig:
    """User-facing settings persisted between sessions."""

    last_database: str | None = None
    last_collection: str | None = None
    visible_columns: list[str] = field(default_factory=list)
    mode: str = field(default_factory=_default_mode)
    local_data_dir: str = field(default_factory=default_local_data_dir)
    username: str = ""
    host_ip: str = "localhost"
    port: int = 27017
    auth_source: str = "admin"

    # When True (and ``mode == 'remote'``), the UI exposes destructive
    # admin actions: create database, drop database, create collection,
    # drop collection. Off by default so a careless click on a production
    # MongoDB server can't wipe a collection. Standalone mode ignores
    # this flag and always allows admin actions on the local files.
    admin_access: bool = False

    # Per-connection "last opened" memory. Keys identify a specific backend
    # (e.g. ``"remote:1.2.3.4:27017"`` or ``"local:/home/me/wetlab"``) so each
    # MongoDB server / standalone folder remembers its own last database +
    # collection independently. The legacy top-level ``last_database`` /
    # ``last_collection`` fields are kept for one-shot migration only.
    last_selection_by_key: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Anything from the JSON file we don't recognise is round-tripped here
    # so older / newer fields aren't silently lost.
    extras: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Per-connection "last opened" helpers
    # ------------------------------------------------------------------
    def get_last_selection(self, key: str) -> dict[str, Any] | None:
        """Return the saved selection for ``key``, or ``None`` if absent."""
        if not key:
            return None
        entry = self.last_selection_by_key.get(key)
        return dict(entry) if isinstance(entry, dict) else None

    def set_last_selection(
        self,
        key: str,
        *,
        last_database: str | None = None,
        last_collection: str | None = None,
        visible_columns: list[str] | None = None,
    ) -> None:
        """Update (or create) the saved selection bucket for ``key``.

        Only non-``None`` arguments overwrite the existing values, so callers
        can update one field without clobbering the others.
        """
        if not key:
            return
        bucket = self.last_selection_by_key.setdefault(key, {})
        if last_database is not None:
            bucket["last_database"] = last_database
        if last_collection is not None:
            bucket["last_collection"] = last_collection
        if visible_columns is not None:
            bucket["visible_columns"] = list(visible_columns)

    @classmethod
    def field_names(cls) -> set[str]:
        """Names of declared (non-extras) fields."""
        return {f.name for f in fields(cls) if f.name != "extras"}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AppConfig":
        """Build an :class:`AppConfig` from a (possibly partial) dict."""
        if not data:
            return cls()
        known = cls.field_names()
        kwargs = {k: v for k, v in data.items() if k in known}
        extras = {k: v for k, v in data.items() if k not in known}
        cfg = cls(**kwargs)
        cfg.extras = extras
        return cfg

    @classmethod
    def load(cls, path: str = CONFIG_FILENAME) -> "AppConfig":
        """Load from ``path``; missing or invalid files yield defaults."""
        if not os.path.exists(path):
            return cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        return cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (extras included, in declaration order)."""
        out: dict[str, Any] = {}
        for f in fields(self):
            if f.name == "extras":
                continue
            out[f.name] = getattr(self, f.name)
        out.update(self.extras)
        return out

    def save(self, path: str = CONFIG_FILENAME) -> None:
        """Write to ``path`` atomically (via a sibling ``.tmp`` file)."""
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        os.replace(tmp, path)


__all__ = ["AppConfig", "CONFIG_FILENAME"]
