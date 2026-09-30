"""CP-SAT vs exhaustive oracle parity on handoff fixtures O01–O06."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("ortools")

from wetlabdb.sar.optimizer.cpsat import OptimizerCancelled, solve_case as solve_case_cpsat
from wetlabdb.sar.optimizer.oracle import solve_case as solve_case_oracle

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "sar_alignment_handoff_v1"
    / "sar_alignment_handoff_v1"
    / "tests"
    / "sar_alignment_optimizer_cases_v1.json"
)


@pytest.fixture(scope="module")
def optimizer_fixture():
    return json.loads(FIXTURE.read_text())


@pytest.mark.parametrize("case_id", ["O01", "O02", "O03", "O04", "O05", "O06"])
def test_cpsat_matches_oracle(optimizer_fixture, case_id):
    levels = len(optimizer_fixture["objective_levels"])
    case = next(c for c in optimizer_fixture["cases"] if c["id"] == case_id)
    oracle = solve_case_oracle(case, levels)
    cpsat = solve_case_cpsat(case, levels)
    assert cpsat["status"] == oracle["status"]
    assert cpsat["optimum"] == oracle["optimum"]
    assert cpsat["evaluated"] == oracle["evaluated"]
    assert cpsat["feasible"] == oracle["feasible"]
    assert sorted(map(json.dumps, cpsat["selections"])) == sorted(
        map(json.dumps, oracle["selections"])
    )


def test_cancel_flag_aborts(optimizer_fixture):
    levels = len(optimizer_fixture["objective_levels"])
    case = optimizer_fixture["cases"][0]
    with pytest.raises(OptimizerCancelled):
        solve_case_cpsat(case, levels, cancel_flag=lambda: True)
