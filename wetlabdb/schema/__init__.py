"""Shared document schemas used by the API, SPA, and (temporarily) Tk."""

from __future__ import annotations

from wetlabdb.schema.compound import (
    COMPOUND_FORM,
    CSV_IDENTIFIER_COLUMNS,
    DEFAULT_VISIBLE_COLUMNS,
    SEARCH_RESULT_COLUMNS,
    compound_form,
    default_compound_document,
)

__all__ = [
    "COMPOUND_FORM",
    "CSV_IDENTIFIER_COLUMNS",
    "DEFAULT_VISIBLE_COLUMNS",
    "SEARCH_RESULT_COLUMNS",
    "compound_form",
    "default_compound_document",
]
