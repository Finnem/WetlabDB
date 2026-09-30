"""Tests for Mongo compound list query builders."""

from __future__ import annotations

from wetlabdb.services.compound_meta import DELETED_AT
from wetlabdb.storage.compound_queries import build_compound_text_query, merge_cursor


def test_active_only_when_no_term():
    q = build_compound_text_query("", "All")
    assert q == {DELETED_AT: {"$exists": False}}


def test_specific_column_regex():
    q = build_compound_text_query("aspirin", "Name")
    assert q[DELETED_AT] == {"$exists": False}
    assert q["Name"]["$regex"] == "aspirin"
    assert q["Name"]["$options"] == "i"


def test_all_columns_uses_or():
    q = build_compound_text_query("50-78", "All")
    assert "$and" in q
    assert any("$or" in clause for clause in q["$and"])


def test_merge_cursor_adds_id_gt():
    base = build_compound_text_query("x", "Name")
    merged = merge_cursor(base, "abc")
    assert "$and" in merged
    assert {"_id": {"$gt": "abc"}} in merged["$and"]
