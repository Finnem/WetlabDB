"""Molecular acceptance cases (Slice 3 gate)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from wetlabdb.sar.pipeline.runner import run_molecular_case

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "sar_alignment_handoff_v1"
    / "sar_alignment_handoff_v1"
    / "tests"
    / "sar_alignment_molecular_cases_v1.json"
)

# Initial release gate from test plan (automatable subset).
SLICE3_CASE_IDS = [
    "M01",
    "M02",
    "M04",
    "M07",
    "M08",
    "M09",
    "M10",
    "M11",
    "M12",
    "M15",
    "M16",
    "M18",
    "M19",
]

MAY_UNSUPPORTED = frozenset({"M05", "M06", "M13", "M14", "M20"})


def _expected_allows(actual: str, expected: str) -> bool:
    if expected == actual:
        return True
    if expected == "OPTIMAL_OR_EXPLICIT_UNSUPPORTED":
        return actual in ("OPTIMAL", "UNSUPPORTED")
    if expected == "VALID_TEMPLATE_OR_EXPLICIT_UNSUPPORTED":
        return actual in ("VALID", "UNSUPPORTED")
    if expected == "VALID_OR_EXPLICIT_INFEASIBLE_AT_SIZE":
        return actual in ("VALID", "INFEASIBLE")
    if expected == "INFEASIBLE_OR_USER_VISIBLE_UNMATCHED":
        return actual in ("INFEASIBLE_OR_USER_VISIBLE_UNMATCHED", "INFEASIBLE")
    if expected == "TWO_VALID_MODES":
        return actual in ("UNSUPPORTED", "VALID", "OPTIMAL")
    return False


@pytest.fixture(scope="module")
def molecular_fixture():
    return json.loads(FIXTURE.read_text())


@pytest.mark.parametrize("case_id", SLICE3_CASE_IDS)
def test_slice3_molecular_gate(molecular_fixture, case_id):
    case = next(c for c in molecular_fixture["cases"] if c["id"] == case_id)
    expected = case["expected"]["result"]
    result = run_molecular_case(case)
    assert _expected_allows(result.status, expected), (
        f"{case_id}: got {result.status!r}, expected {expected!r} — {result.user_message}"
    )


@pytest.mark.parametrize("case_id", sorted(MAY_UNSUPPORTED))
def test_advanced_cases_honest_status(molecular_fixture, case_id):
    case = next(c for c in molecular_fixture["cases"] if c["id"] == case_id)
    expected = case["expected"]["result"]
    result = run_molecular_case(case)
    assert _expected_allows(result.status, expected)


def test_m01_core_alignment_count(molecular_fixture):
    case = next(c for c in molecular_fixture["cases"] if c["id"] == "M01")
    result = run_molecular_case(case)
    assert result.status == "OPTIMAL"
    assert len(result.layouts) == 3
    assert result.certificate == "candidate_selection_optimal"


def test_m04_scaffold_bioisostere(molecular_fixture):
    case = next(c for c in molecular_fixture["cases"] if c["id"] == "M04")
    result = run_molecular_case(case)
    assert result.status == "OPTIMAL"
    assert len(result.layouts) == 2
    assert result.details.get("mode") == "scaffold_replacement"


def test_m02_ring_atom_replacements(molecular_fixture):
    case = next(c for c in molecular_fixture["cases"] if c["id"] == "M02")
    result = run_molecular_case(case)
    assert result.status == "OPTIMAL"
    assert len(result.layouts) == 3
    assert result.details.get("mode") == "ring_atom_replacements"


def test_m02_rejects_bromo_for_chloro():
    case = {
        "id": "M02-negative",
        "comparison": {
            "mode": "ring_atom_replacements",
            "reference": "H1",
            "allowed_atom_changes": ["aromatic C <-> aromatic N"],
        },
        "molecules": [
            {"id": "H1", "smiles": "Nc1ncc(Cl)cc1"},
            {"id": "H2", "smiles": "Nc1ncc(Br)nc1"},
        ],
    }
    result = run_molecular_case(case)
    assert result.status == "INFEASIBLE_OR_USER_VISIBLE_UNMATCHED"


def test_m11_outlier_not_silent(molecular_fixture):
    case = next(c for c in molecular_fixture["cases"] if c["id"] == "M11")
    result = run_molecular_case(case)
    assert result.status == "INFEASIBLE_OR_USER_VISIBLE_UNMATCHED"
