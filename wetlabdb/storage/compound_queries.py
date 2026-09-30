"""MongoDB query builders for compound list text filters."""

from __future__ import annotations

import re

from wetlabdb.schema.compound import COMPOUND_FORM
from wetlabdb.services.compound_meta import DELETED_AT
from wetlabdb.storage.ids import coerce_id


def active_only_clause() -> dict:
    return {DELETED_AT: {"$exists": False}}


def build_compound_text_query(
    q: str | None,
    column: str | None,
) -> dict:
    """Build a Mongo filter matching :meth:`CompoundService.list_filtered` semantics."""
    term = (q or "").strip()
    col = (column or "").strip()
    base = active_only_clause()
    if not term:
        return base

    pattern = re.escape(term)
    regex = {"$regex": pattern, "$options": "i"}
    if col and col.lower() != "all":
        return {**base, col: regex}

    or_clauses: list[dict] = [{field: regex} for field in COMPOUND_FORM]
    or_clauses.append(
        {
            "$expr": {
                "$regexMatch": {
                    "input": {"$toString": "$_id"},
                    "regex": pattern,
                    "options": "i",
                }
            }
        }
    )
    return {"$and": [base, {"$or": or_clauses}]}


def merge_cursor(query: dict, after_id: str | None) -> dict:
    if not after_id:
        return query
    cursor_clause = {"_id": {"$gt": coerce_id(after_id)}}
    if "$and" in query:
        return {"$and": [*query["$and"], cursor_clause]}
    return {"$and": [query, cursor_clause]}


__all__ = ["active_only_clause", "build_compound_text_query", "merge_cursor"]
