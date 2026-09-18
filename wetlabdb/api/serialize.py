"""JSON-safe document helpers for the HTTP API."""

from __future__ import annotations

import json
from typing import Any

from wetlabdb.storage.json_codec import MongoJSONEncoder


def serialize_doc(doc: dict | None) -> dict | None:
    """Return a JSON-safe copy with ``_id`` coerced to ``str``."""
    if doc is None:
        return None
    raw = json.loads(json.dumps(doc, cls=MongoJSONEncoder))
    if isinstance(raw, dict) and "_id" in raw:
        raw["_id"] = str(raw["_id"])
    return raw


def serialize_docs(docs: list[dict]) -> list[dict]:
    return [d for d in (serialize_doc(doc) for doc in docs) if d is not None]


def doc_row(doc: dict, columns: list[str]) -> list[Any]:
    """Project ``doc`` onto ``columns`` (missing keys become empty strings)."""
    safe = serialize_doc(doc) or {}
    return [safe.get(col, "") for col in columns]


__all__ = ["doc_row", "serialize_doc", "serialize_docs"]
