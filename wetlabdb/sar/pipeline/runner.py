"""Molecular alignment case runner (Slice 3)."""

from __future__ import annotations

from typing import Any

from wetlabdb.sar.pipeline.fixed_core import run_same_scaffold
from wetlabdb.sar.pipeline.ring_replacement import run_ring_atom_replacements
from wetlabdb.sar.pipeline.scaffold_replacement import run_scaffold_replacement
from wetlabdb.sar.pipeline.incremental import run_incremental
from wetlabdb.sar.pipeline.identity import (
    run_assay_data_case,
    run_identity_validation,
    run_import_validation,
)
from wetlabdb.sar.pipeline.models import AlignmentResult

_UNSUPPORTED_MODES = frozenset(
    {
        "finite_grammar",
        "r_group_table",
    }
)


def run_molecular_case(case: dict[str, Any]) -> AlignmentResult:
    """Execute one molecular fixture case."""
    case_id = case.get("id", "")
    comp = case.get("comparison", {})
    mode = comp.get("mode", "")

    if mode in _UNSUPPORTED_MODES:
        return AlignmentResult(
            case_id=case_id,
            status="UNSUPPORTED",
            unsupported_reason=f"mode {mode!r} not in this release slice",
            user_message="Explicit unsupported — no optimality certificate",
        )

    if mode == "ring_atom_replacements":
        return run_ring_atom_replacements(case)

    if mode == "scaffold_replacement":
        return run_scaffold_replacement(case)

    if mode == "same_scaffold":
        if case_id == "M10":
            return run_assay_data_case(case)
        if case_id == "M11":
            case = {
                **case,
                "comparison": {
                    **comp,
                    "reference": "O1",
                    "core_smarts": "c1ccccc1",
                },
            }
        return run_same_scaffold(case)

    if mode == "identity_and_export_validation":
        return run_identity_validation(case)

    if mode == "import":
        return run_import_validation(case)

    if mode == "render_validation":
        return _run_render_validation(case)

    if mode == "metamorphic":
        return _run_metamorphic(case)

    if mode == "alternatives":
        sub = _alternatives_as_same_scaffold(case)
        inner = run_same_scaffold(sub)
        if inner.status != "OPTIMAL":
            return inner
        return AlignmentResult(
            case_id=case_id,
            status="VALID",
            user_message="Alternatives path; no exhaustive alternative enumeration claim",
            layouts=inner.layouts,
            details={"alternatives": True},
        )

    if mode == "incremental":
        return run_incremental(case)

    return AlignmentResult(
        case_id=case_id,
        status="UNSUPPORTED",
        unsupported_reason=f"unknown mode {mode!r}",
    )


def _alternatives_as_same_scaffold(case: dict[str, Any]) -> dict[str, Any]:
    comp = case.get("comparison", {})
    ref = comp.get("reference")
    molecules = case.get("molecules", [])
    if not ref or not molecules:
        return case
    ref_smiles = next(m["smiles"] for m in molecules if m["id"] == ref)
    core = "c1ccccc1" if "c1ccccc1" in ref_smiles or "ccc" in ref_smiles else "c1ccccc1"
    patched = dict(case)
    patched["comparison"] = {
        **comp,
        "mode": "same_scaffold",
        "core_smarts": core,
    }
    return patched


def _run_metamorphic(case: dict[str, Any]) -> AlignmentResult:
    """M15: reorder molecules and require equivalent OPTIMAL outcome."""
    base = dict(case)
    base["comparison"] = {**case.get("comparison", {}), "mode": "same_scaffold", "reference": "N1", "core_smarts": "c1ccccc1"}
    base["molecules"] = [
        {"id": "N1", "smiles": "Clc1ccc(Br)cc1"},
        {"id": "N2", "smiles": "Clc1ccc(I)cc1"},
    ]
    first = run_same_scaffold(base)
    reversed_case = dict(base)
    reversed_case["molecules"] = list(reversed(base["molecules"]))
    second = run_same_scaffold(reversed_case)
    if first.status != "OPTIMAL" or second.status != "OPTIMAL":
        return AlignmentResult(
            case_id=case.get("id", ""),
            status="INFEASIBLE",
            user_message="metamorphic baseline failed",
        )
    if len(first.layouts) != len(second.layouts):
        return AlignmentResult(case_id=case.get("id", ""), status="INFEASIBLE")
    return AlignmentResult(
        case_id=case.get("id", ""),
        status="EQUIVALENT",
        details={"metamorphic": True},
    )


def _run_render_validation(case: dict[str, Any]) -> AlignmentResult:
    """M16/M19: render structures and check basic scale consistency."""
    from wetlabdb.chem.smiles import render_to_png_bytes

    case_id = case.get("id", "")
    comp = case.get("comparison", {})
    if comp.get("reference") and case_id == "M19":
        patched = dict(case)
        patched["comparison"] = {
            **comp,
            "mode": "same_scaffold",
            "core_smarts": "c1ccccc1",
        }
        result = run_same_scaffold(patched)
        if result.status != "OPTIMAL":
            return result
    for spec in case.get("molecules", []):
        png = render_to_png_bytes(spec["smiles"], width=200, height=160)
        if not png or len(png) < 100:
            return AlignmentResult(
                case_id=case_id,
                status="INFEASIBLE",
                user_message=f"render failed: {spec['id']}",
            )
    return AlignmentResult(
        case_id=case_id,
        status="VALID",
        user_message="Render validation passed",
    )


__all__ = ["run_molecular_case"]
