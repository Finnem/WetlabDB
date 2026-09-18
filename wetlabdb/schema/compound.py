"""Default compound document schema.

Kept independent of Tk so the web API, SPA, and tests share one field list.
"""

from __future__ import annotations

from typing import Any


COMPOUND_FORM: dict[str, dict[str, Any]] = {
    "Name": {"type": "string", "default": ""},
    "SMILES": {"type": "string", "default": ""},
    "CAS Nr": {"type": "string", "default": ""},
    "Storage Location": {"type": "string", "default": ""},
    "1H NMR exists": {"type": "boolean", "default": False},
    "1H NMR Identity confirmed": {"type": "boolean", "default": False},
    "Pure": {"type": "boolean", "default": False},
    "Turbi Solubility [mM]": {"type": "float", "default": 0.0},
    "DMSO Solubility [mM]": {"type": "float", "default": 0.0},
    "Acetonitrile Solubility [mM]": {"type": "float", "default": 0.0},
    "Crystal Structure exists": {"type": "boolean", "default": False},
    "GSH Reactivity H-life [h]": {"type": "float", "default": 0.0},
    "DTNB Reactivity k2 [M^-1 s^-1]": {"type": "float", "default": 0.0},
}

# Backwards-compatible alias used by the Tk form.
compound_form = COMPOUND_FORM

DEFAULT_VISIBLE_COLUMNS: list[str] = [
    "Name",
    "SMILES",
    "CAS Nr",
    "Storage Location",
]

CSV_IDENTIFIER_COLUMNS: list[str] = ["CAS Nr", "Name", "SMILES"]

SEARCH_RESULT_COLUMNS: list[str] = [
    "Name",
    "SMILES",
    "CAS Nr",
    "Storage Location",
    "Similarity",
]


def default_compound_document() -> dict[str, Any]:
    """Return a new-document dict with typed defaults from :data:`COMPOUND_FORM`."""
    initial: dict[str, Any] = {}
    for key, field_info in COMPOUND_FORM.items():
        field_type = field_info["type"]
        default_value = field_info["default"]
        if field_type == "boolean":
            initial[key] = bool(default_value)
        elif field_type == "float":
            initial[key] = float(default_value)
        elif field_type == "file":
            initial[key] = None
        else:
            initial[key] = default_value
    return initial


__all__ = [
    "COMPOUND_FORM",
    "CSV_IDENTIFIER_COLUMNS",
    "DEFAULT_VISIBLE_COLUMNS",
    "SEARCH_RESULT_COLUMNS",
    "compound_form",
    "default_compound_document",
]
