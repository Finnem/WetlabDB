"""Validate and apply compound field selection for list APIs."""

from __future__ import annotations

import re

MAX_SELECTED_FIELDS = 50
_FIELD_NAME = re.compile(r"^[^\x00-\x1f$\\]{1,100}$")


class InvalidFieldSelectionError(ValueError):
    """One or more requested field names are not allowed."""


def parse_field_selection(raw: str | None) -> list[str] | None:
    """Parse a comma-separated ``fields`` query parameter."""
    if raw is None or not str(raw).strip():
        return None
    parts = [part.strip() for part in str(raw).split(",")]
    fields: list[str] = []
    for part in parts:
        if not part:
            raise InvalidFieldSelectionError("Empty field name in fields list")
        if part == "_id":
            continue
        if not _FIELD_NAME.match(part):
            raise InvalidFieldSelectionError(f"Invalid field name: {part!r}")
        if part not in fields:
            fields.append(part)
    if len(fields) > MAX_SELECTED_FIELDS:
        raise InvalidFieldSelectionError(
            f"Too many fields (max {MAX_SELECTED_FIELDS})"
        )
    return fields or None


def mongo_projection(fields: list[str]) -> dict:
    proj = {name: 1 for name in fields}
    proj["_id"] = 1
    return proj


def project_documents(docs: list[dict], fields: list[str] | None) -> list[dict]:
    if not fields:
        return docs
    out: list[dict] = []
    for doc in docs:
        row: dict = {"_id": doc.get("_id")}
        for name in fields:
            if name in doc:
                row[name] = doc[name]
        out.append(row)
    return out


__all__ = [
    "InvalidFieldSelectionError",
    "MAX_SELECTED_FIELDS",
    "mongo_projection",
    "parse_field_selection",
    "project_documents",
]
