"""Status/certificate semantics S01–S07 (Slice 7 gate)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from wetlabdb.sar.hardening.completion import (
    certificate_invalidated,
    enumeration_incomplete,
    infeasible_in_template_set,
    mcs_search_incomplete,
    optimization_incomplete,
    optimal_complete,
    render_validation_failure,
    strip_certificate_from_draft,
)
from wetlabdb.sar.hardening.vocabulary import FORBIDDEN_STATUS_BY_CASE, STATUS_CASE_MESSAGES
from wetlabdb.sar.pipeline.runner import run_molecular_case

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "sar_alignment_handoff_v1"
    / "sar_alignment_handoff_v1"
    / "tests"
    / "sar_alignment_molecular_cases_v1.json"
)


@pytest.fixture(scope="module")
def molecular_fixture():
    return json.loads(FIXTURE.read_text())


@pytest.mark.parametrize("case_id", list(STATUS_CASE_MESSAGES))
def test_status_vocabulary_matches_fixture(molecular_fixture, case_id):
    case = next(c for c in molecular_fixture["status_cases"] if c["id"] == case_id)
    assert STATUS_CASE_MESSAGES[case_id] == case["expected_status"]


@pytest.mark.parametrize("case_id", sorted(FORBIDDEN_STATUS_BY_CASE))
def test_forbidden_overclaim_cases_in_fixture(molecular_fixture, case_id):
    case = next(c for c in molecular_fixture["status_cases"] if c["id"] == case_id)
    assert case.get("forbidden_status") == FORBIDDEN_STATUS_BY_CASE[case_id]


def test_s01_m01_optimal_message(molecular_fixture):
    case = next(c for c in molecular_fixture["cases"] if c["id"] == "M01")
    result = run_molecular_case(case)
    assert result.status == "OPTIMAL"
    assert result.user_message == STATUS_CASE_MESSAGES["S01"]
    assert result.certificate == "candidate_selection_optimal"
    assert result.details.get("completion") == "S01"


@pytest.mark.parametrize(
    "policy_fn,case_id,forbidden",
    [
        (enumeration_incomplete, "S02", "OPTIMAL"),
        (mcs_search_incomplete, "S03", "INFEASIBLE"),
        (optimization_incomplete, "S04", "OPTIMAL"),
        (infeasible_in_template_set, "S05", None),
        (render_validation_failure, "S06", "certified export"),
        (certificate_invalidated, "S07", "reuse previous certificate"),
    ],
)
def test_completion_policies(policy_fn, case_id, forbidden):
    policy = policy_fn()
    assert policy.user_message == STATUS_CASE_MESSAGES[case_id]
    assert policy.certificate is None
    if forbidden == "OPTIMAL":
        assert policy.status != "OPTIMAL"
    if forbidden == "INFEASIBLE" and case_id == "S03":
        assert policy.status != "INFEASIBLE"


def test_s07_strip_certificate_from_draft():
    draft = {
        "status": "OPTIMAL",
        "certificate": "candidate_selection_optimal",
        "user_message": "Best layout proven within this template set",
        "layouts": [],
    }
    stripped = strip_certificate_from_draft(draft)
    assert stripped["certificate"] is None
    assert stripped["user_message"] == STATUS_CASE_MESSAGES["S07"]
    assert stripped["status"] == "VALID"
