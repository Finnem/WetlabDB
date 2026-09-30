"""Compound field selection parsing."""

from __future__ import annotations

import pytest

from wetlabdb.services.compound_fields import (
    InvalidFieldSelectionError,
    parse_field_selection,
    project_documents,
)


def test_parse_fields_dedupes():
    assert parse_field_selection("Name, SMILES, Name") == ["Name", "SMILES"]


def test_parse_fields_rejects_empty_segment():
    with pytest.raises(InvalidFieldSelectionError):
        parse_field_selection("Name,,SMILES")


def test_project_documents_subset():
    docs = [{"_id": "1", "Name": "A", "SMILES": "C", "Extra": 1}]
    out = project_documents(docs, ["Name"])
    assert out == [{"_id": "1", "Name": "A"}]
