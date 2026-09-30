"""Slice 6: sidecar approvals and incremental alignment."""

from __future__ import annotations

import time

import pytest

from wetlabdb.sar.pipeline.runner import run_molecular_case
from wetlabdb.sar.sidecar import SarAlignmentSidecar, SidecarConcurrencyError

FIXTURE = (
    __import__("pathlib").Path(__file__).resolve().parents[1]
    / "sar_alignment_handoff_v1"
    / "sar_alignment_handoff_v1"
    / "tests"
    / "sar_alignment_molecular_cases_v1.json"
)


@pytest.fixture(scope="module")
def molecular_fixture():
    import json

    return json.loads(FIXTURE.read_text())


@pytest.fixture
def sidecar(tmp_path):
    return SarAlignmentSidecar.from_settings(
        is_local=True,
        data_dir=str(tmp_path),
        client=None,  # type: ignore[arg-type]
    )


def test_m17_incremental_two_modes(molecular_fixture):
    case = next(c for c in molecular_fixture["cases"] if c["id"] == "M17")
    result = run_molecular_case(case)
    assert result.status == "VALID"
    assert result.details.get("incremental") is True
    assert result.details.get("preserve", {}).get("certificate") is None
    assert result.details.get("base_certificate_not_reused") is True
    assert len(result.layouts) == 4


def test_sidecar_approve_blocks_silent_draft_edit(sidecar):
    project = sidecar.create_project(
        owner="chemist",
        project_id="WetlabDB",
        series_id="Compounds",
        compound_ids=["a"],
        assay_ids=[],
        reference_id="a",
        mode="same_scaffold",
        core_smarts="c1ccccc1",
        snapshot_revision="rev1",
        draft_solution={"status": "OPTIMAL", "layouts": []},
    )
    approved = sidecar.approve(
        project.id,
        expected_version=project.version,
        actor="chemist",
        snapshot_revision="rev1",
    )
    with pytest.raises(SidecarConcurrencyError, match="locked"):
        sidecar.patch_draft(
            approved.id,
            expected_version=approved.version,
            actor="chemist",
            draft_solution={"status": "OPTIMAL", "layouts": [{"x": 1}]},
        )


def test_sidecar_strip_certificate_on_edit(sidecar):
    project = sidecar.create_project(
        owner="chemist",
        project_id="WetlabDB",
        series_id="Compounds",
        compound_ids=["a"],
        assay_ids=[],
        reference_id="a",
        mode="same_scaffold",
        core_smarts="c1ccccc1",
        snapshot_revision="rev1",
        draft_solution={
            "status": "OPTIMAL",
            "certificate": "candidate_selection_optimal",
            "user_message": "Best layout proven within this template set",
            "layouts": [],
        },
    )
    updated = sidecar.patch_draft(
        project.id,
        expected_version=project.version,
        actor="chemist",
        draft_solution={
            "status": "OPTIMAL",
            "certificate": "candidate_selection_optimal",
            "user_message": "edited",
            "layouts": [{"molecule_id": "a"}],
        },
        force_unapproved_edit=True,
    )
    assert updated.draft_solution.get("certificate") is None
    assert "invalid" in updated.draft_solution.get("user_message", "").lower()


def test_sidecar_revision_mismatch_blocks_approval(sidecar):
    project = sidecar.create_project(
        owner="chemist",
        project_id="WetlabDB",
        series_id="Compounds",
        compound_ids=["a"],
        assay_ids=[],
        reference_id="a",
        mode="same_scaffold",
        core_smarts="c1ccccc1",
        snapshot_revision="rev1",
        draft_solution={"status": "OPTIMAL", "layouts": []},
    )
    with pytest.raises(SidecarConcurrencyError, match="revision mismatch"):
        sidecar.approve(
            project.id,
            expected_version=project.version,
            actor="chemist",
            snapshot_revision="rev2",
        )


def test_sidecar_lists_recent_projects_newest_first(sidecar):
    older = sidecar.create_project(
        owner="chemist",
        project_id="WetlabDB",
        series_id="Compounds",
        compound_ids=["a"],
        assay_ids=[],
        reference_id="a",
        mode="same_scaffold",
        core_smarts="c1ccccc1",
        snapshot_revision="rev1",
        draft_solution={"status": "OPTIMAL", "layouts": []},
    )
    time.sleep(0.02)
    newer = sidecar.create_project(
        owner="chemist",
        project_id="WetlabDB",
        series_id="Compounds",
        compound_ids=["b"],
        assay_ids=[],
        reference_id="b",
        mode="same_scaffold",
        core_smarts="c1ccccc1",
        snapshot_revision="rev2",
        draft_solution={"status": "OPTIMAL", "layouts": []},
    )
    listed = sidecar.list_projects(project_id="WetlabDB", series_id="Compounds")
    assert [p.id for p in listed[:2]] == [newer.id, older.id]
    assert sidecar.list_projects(project_id="OtherDB", series_id="Compounds") == []
