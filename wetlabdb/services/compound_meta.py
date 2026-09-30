"""Internal compound document fields (soft delete, not user schema)."""

from __future__ import annotations

from datetime import datetime, timezone

DELETED_AT = "_wetlabdb_deleted_at"
DELETED_BY = "_wetlabdb_deleted_by"

META_FIELD_NAMES: frozenset[str] = frozenset({DELETED_AT, DELETED_BY})


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def is_soft_deleted(doc: dict | None) -> bool:
    if not doc:
        return False
    return bool(doc.get(DELETED_AT))


def without_meta_fields(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k not in META_FIELD_NAMES}


__all__ = [
    "DELETED_AT",
    "DELETED_BY",
    "META_FIELD_NAMES",
    "is_soft_deleted",
    "utc_now_iso",
    "without_meta_fields",
]
