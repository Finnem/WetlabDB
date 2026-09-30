"""JSON-safe audit event payloads for HTTP responses."""

from __future__ import annotations

import json
from typing import Any

from wetlabdb.storage.json_codec import MongoJSONEncoder


def serialize_audit_events(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Coerce Mongo ``ObjectId`` / datetime values to JSON-safe types."""
    encoded = json.dumps(rows, cls=MongoJSONEncoder)
    out = json.loads(encoded)
    if not isinstance(out, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for row in out:
        if not isinstance(row, dict):
            continue
        row.pop("_id", None)
        cleaned.append(row)
    return cleaned


__all__ = ["serialize_audit_events"]
