"""Strict validation for database and collection identifiers."""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

CATALOG_NAME_MAX_LEN = 64
_CATALOG_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class InvalidCatalogNameError(ValueError):
    """Raised when a database or collection name is not allowed."""


def validate_catalog_name(
    name: str,
    *,
    kind: Literal["database", "collection"],
) -> str:
    """Return a normalized name or raise :class:`InvalidCatalogNameError`."""
    label = "Database" if kind == "database" else "Collection"
    if name is None:
        raise InvalidCatalogNameError(f"{label} name is required")
    if not isinstance(name, str):
        raise InvalidCatalogNameError(f"{label} name must be a string")
    if name != name.strip():
        raise InvalidCatalogNameError(f"{label} name must not have leading or trailing spaces")
    cleaned = name.strip()
    if not cleaned:
        raise InvalidCatalogNameError(f"{label} name is required")
    if len(cleaned) > CATALOG_NAME_MAX_LEN:
        raise InvalidCatalogNameError(
            f"{label} name must be at most {CATALOG_NAME_MAX_LEN} characters"
        )
    normalized = unicodedata.normalize("NFC", cleaned)
    if normalized != cleaned:
        raise InvalidCatalogNameError(f"{label} name must use plain ASCII characters")
    if cleaned in {".", ".."}:
        raise InvalidCatalogNameError(f"Invalid {label.lower()} name")
    if "/" in cleaned or "\\" in cleaned:
        raise InvalidCatalogNameError(f"{label} name must not contain path separators")
    if not _CATALOG_NAME_RE.match(cleaned):
        raise InvalidCatalogNameError(
            f"{label} name may only contain letters, digits, underscores, and hyphens"
        )
    return cleaned


__all__ = [
    "CATALOG_NAME_MAX_LEN",
    "InvalidCatalogNameError",
    "validate_catalog_name",
]
