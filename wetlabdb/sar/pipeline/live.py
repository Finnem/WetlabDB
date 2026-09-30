"""Run alignment pipeline from a live SeriesSnapshot."""

from __future__ import annotations

from typing import Any

from wetlabdb.sar.pipeline.isomorphisms import normalize_scaffold_element_mode
from wetlabdb.sar.pipeline.models import AlignmentResult
from wetlabdb.sar.pipeline.runner import run_molecular_case


def build_alignment_case(
    snapshot: dict[str, Any],
    *,
    reference_id: str,
    mode: str = "same_scaffold",
    core_smarts: str = "c1ccccc1",
    ignore_bond_order: bool = False,
    scaffold_element_mode: str = "from_smarts",
    poses: dict[str, str] | None = None,
) -> dict[str, Any]:
    molecules: list[dict[str, str]] = []
    empty: list[str] = []
    pose_blocks = poses or {}
    for compound in snapshot.get("compounds", []):
        cid = compound["id"]
        smiles = str(compound.get("structure", {}).get("value") or "").strip()
        if not smiles:
            empty.append(cid)
            continue
        entry: dict[str, str] = {"id": cid, "smiles": smiles}
        block = str(pose_blocks.get(cid) or "").strip()
        if block:
            entry["molblock"] = pose_blocks[cid]
        molecules.append(entry)
    if empty:
        raise ValueError(f"Empty SMILES (unsupported): {', '.join(empty)}")
    if not molecules:
        raise ValueError("No compounds with structures in snapshot")
    ids = {m["id"] for m in molecules}
    if reference_id not in ids:
        raise ValueError(f"Reference {reference_id!r} is not in the snapshot selection")
    comparison: dict[str, Any] = {
        "mode": mode,
        "reference": reference_id,
    }
    if mode == "same_scaffold":
        comparison["core_smarts"] = core_smarts.strip()
        comparison["ignore_bond_order"] = bool(ignore_bond_order)
        comparison["scaffold_element_mode"] = normalize_scaffold_element_mode(scaffold_element_mode)
    elif mode == "ring_atom_replacements":
        comparison["allowed_atom_changes"] = ["aromatic C <-> aromatic N"]
        comparison["allowed_region"] = "selected six-membered aromatic ring"
    else:
        raise ValueError(f"Unsupported alignment mode {mode!r}")
    return {
        "id": "live-run",
        "comparison": comparison,
        "molecules": molecules,
    }


def build_same_scaffold_case(
    snapshot: dict[str, Any],
    *,
    reference_id: str,
    core_smarts: str,
    ignore_bond_order: bool = False,
    scaffold_element_mode: str = "from_smarts",
    poses: dict[str, str] | None = None,
) -> dict[str, Any]:
    return build_alignment_case(
        snapshot,
        reference_id=reference_id,
        mode="same_scaffold",
        core_smarts=core_smarts,
        ignore_bond_order=ignore_bond_order,
        scaffold_element_mode=scaffold_element_mode,
        poses=poses,
    )


def run_from_snapshot(
    snapshot: dict[str, Any],
    *,
    reference_id: str,
    mode: str = "same_scaffold",
    core_smarts: str = "c1ccccc1",
    ignore_bond_order: bool = False,
    scaffold_element_mode: str = "from_smarts",
    poses: dict[str, str] | None = None,
    progress: Any | None = None,
) -> AlignmentResult:
    case = build_alignment_case(
        snapshot,
        reference_id=reference_id,
        mode=mode or "same_scaffold",
        core_smarts=core_smarts or "c1ccccc1",
        ignore_bond_order=ignore_bond_order,
        scaffold_element_mode=scaffold_element_mode,
        poses=poses,
    )
    if progress is not None and (mode or "same_scaffold") == "same_scaffold":
        from wetlabdb.sar.pipeline.fixed_core import run_same_scaffold

        return run_same_scaffold(case, progress=progress)
    return run_molecular_case(case)


def result_to_response(result: AlignmentResult, snapshot: dict[str, Any]) -> dict[str, Any]:
    display_by_id = {
        c["id"]: c.get("display_id", c["id"]) for c in snapshot.get("compounds", [])
    }
    return {
        "status": result.status,
        "certificate": result.certificate,
        "user_message": result.user_message,
        "unsupported_reason": result.unsupported_reason,
        "objective": result.objective,
        "details": result.details,
        "snapshot_revision": snapshot.get("source", {}).get("revision"),
        "layouts": [
            {
                "molecule_id": layout.molecule_id,
                "display_id": display_by_id.get(layout.molecule_id, layout.molecule_id),
                "smiles": layout.smiles,
                "molblock": layout.molblock,
                "core_atom_indices": list(layout.core_atom_indices),
                "core_atom_count": len(layout.core_atom_indices),
            }
            for layout in result.layouts
        ],
    }


__all__ = [
    "build_alignment_case",
    "build_same_scaffold_case",
    "result_to_response",
    "run_from_snapshot",
]
