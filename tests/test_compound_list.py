"""Unit tests for compound pagination helper."""

from __future__ import annotations

from wetlabdb.services.compound_list import paginate_compounds


def test_paginate_stable_cursor():
    docs = [{"_id": f"{index:02d}", "Name": f"C{index}"} for index in range(5)]
    page1 = paginate_compounds(docs, limit=2, cursor=None)
    assert len(page1.compounds) == 2
    assert page1.next_cursor == "01"
    page2 = paginate_compounds(docs, limit=2, cursor=page1.next_cursor)
    assert [d["_id"] for d in page2.compounds] == ["02", "03"]
