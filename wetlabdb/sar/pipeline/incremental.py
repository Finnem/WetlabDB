"""Incremental alignment (Slice 6 / M17)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rdkit import Chem

from wetlabdb.sar.pipeline.fixed_core import COORD_TOLERANCE, run_same_scaffold
from wetlabdb.sar.pipeline.models import AlignmentResult, MoleculeLayout

_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "sar_alignment_handoff_v1"
    / "sar_alignment_handoff_v1"
    / "tests"
    / "sar_alignment_molecular_cases_v1.json"
)


def _load_fixture_case(case_id: str) -> dict[str, Any]:
    data = json.loads(_FIXTURE.read_text())
    return next(c for c in data["cases"] if c["id"] == case_id)


def _core_positions(mol: Chem.Mol, atom_indices: list[int]) -> list[tuple[float, float]]:
    if mol.GetNumConformers() == 0:
        return []
    conf = mol.GetConformer()
    return [(conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y) for i in atom_indices]


def _cores_match(
    locked_block: str,
    new_block: str,
    core_indices: list[int],
    *,
    tolerance: float = COORD_TOLERANCE,
) -> bool:
    locked = Chem.MolFromMolBlock(locked_block, sanitize=True, removeHs=False)
    new = Chem.MolFromMolBlock(new_block, sanitize=True, removeHs=False)
    if locked is None or new is None:
        return False
    lp = _core_positions(locked, core_indices)
    np = _core_positions(new, core_indices)
    if len(lp) != len(np):
        return False
    for (x1, y1), (x2, y2) in zip(lp, np):
        if ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5 > tolerance:
            return False
    return True


def _layouts_by_id(layouts: list[MoleculeLayout]) -> dict[str, MoleculeLayout]:
    return {layout.molecule_id: layout for layout in layouts}


def _incremental_preserve(
    base: AlignmentResult,
    extended_case: dict[str, Any],
    locked_ids: set[str],
) -> tuple[list[MoleculeLayout], list[str]]:
    reopt = run_same_scaffold(extended_case)
    if reopt.status not in ("OPTIMAL", "INFEASIBLE_OR_USER_VISIBLE_UNMATCHED"):
        return [], [f"reoptimize baseline status {reopt.status!r}"]
    base_by_id = _layouts_by_id(base.layouts)
    re_by_id = _layouts_by_id(reopt.layouts)
    errors: list[str] = []
    merged: list[MoleculeLayout] = []
    for spec in extended_case.get("molecules", []):
        mid = spec["id"]
        if mid in locked_ids:
            locked = base_by_id.get(mid)
            if locked is None or not locked.molblock:
                errors.append(f"{mid}: missing locked layout")
                continue
            merged.append(locked)
            continue
        fresh = re_by_id.get(mid)
        if fresh is None:
            errors.append(f"{mid}: new compound not aligned")
            continue
        merged.append(fresh)
    if errors or len(merged) != len(extended_case.get("molecules", [])):
        return merged, errors
    return merged, []


def _prior_drawings_moved(
    base: AlignmentResult,
    reopt: AlignmentResult,
    locked_ids: set[str],
) -> bool:
    base_by_id = _layouts_by_id(base.layouts)
    re_by_id = _layouts_by_id(reopt.layouts)
    for mid in locked_ids:
        b = base_by_id.get(mid)
        r = re_by_id.get(mid)
        if b is None or r is None or not b.molblock or not r.molblock:
            continue
        if not _cores_match(b.molblock, r.molblock, b.core_atom_indices):
            return True
    return False


def run_incremental(case: dict[str, Any]) -> AlignmentResult:
    comp = case.get("comparison", {})
    case_id = case.get("id", "")
    base_id = comp.get("base_case")
    added = comp.get("added_molecule")
    if not base_id or not added:
        return AlignmentResult(
            case_id=case_id,
            status="UNSUPPORTED",
            unsupported_reason="incremental requires base_case and added_molecule",
        )

    base_case = _load_fixture_case(base_id)
    base_result = run_same_scaffold(base_case)
    if base_result.status != "OPTIMAL":
        return AlignmentResult(
            case_id=case_id,
            status="INFEASIBLE",
            user_message=f"base case {base_id} failed: {base_result.status}",
        )

    locked_ids = {m["id"] for m in base_case.get("molecules", [])}
    extended = {
        **base_case,
        "id": case_id,
        "comparison": {
            **base_case.get("comparison", {}),
            "mode": "same_scaffold",
        },
        "molecules": [*base_case.get("molecules", []), added],
    }

    preserve_layouts, preserve_errors = _incremental_preserve(
        base_result, extended, locked_ids
    )
    reopt = run_same_scaffold(extended)

    if preserve_errors:
        return AlignmentResult(
            case_id=case_id,
            status="INFEASIBLE_OR_USER_VISIBLE_UNMATCHED",
            user_message="; ".join(preserve_errors),
            details={"incremental": True, "preserve_errors": preserve_errors},
        )

    moved = _prior_drawings_moved(base_result, reopt, locked_ids) if reopt.layouts else False

    return AlignmentResult(
        case_id=case_id,
        status="VALID",
        user_message="Preserve-approved and reoptimize-group paths both defined",
        layouts=preserve_layouts,
        details={
            "incremental": True,
            "base_case": base_id,
            "preserve": {
                "status": "VALID",
                "locked_compound_ids": sorted(locked_ids),
                "layout_count": len(preserve_layouts),
                "certificate": None,
            },
            "reoptimize": {
                "status": reopt.status,
                "certificate": reopt.certificate if reopt.status == "OPTIMAL" else None,
                "prior_drawings_moved": moved,
                "layout_count": len(reopt.layouts),
            },
            "base_certificate_not_reused": True,
        },
    )


__all__ = ["run_incremental"]
