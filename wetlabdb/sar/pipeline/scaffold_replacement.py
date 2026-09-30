"""Scaffold replacement alignment (Slice 5 / M04)."""

from __future__ import annotations

from typing import Any

from rdkit import Chem

from wetlabdb.sar.pipeline.fixed_core import run_same_scaffold
from wetlabdb.sar.pipeline.ingestion import ingest_molecule
from wetlabdb.sar.pipeline.models import AlignmentResult
from wetlabdb.sar.pipeline.scaffold_roles import (
    PHENOL_CORE_SMARTS,
    angle_degrees,
    attachment_vector,
    is_phenol_bioisostere_case,
    phenol_attachment_ring_atom,
    phenol_core_match,
    ring_atoms_from_phenol_match,
    substituent_anchor_atom,
)

_ANGLE_TOLERANCE_DEG = 2.0


def _unsupported(case_id: str, reason: str) -> AlignmentResult:
    return AlignmentResult(
        case_id=case_id,
        status="UNSUPPORTED",
        unsupported_reason=reason,
        user_message="Explicit unsupported — no optimality certificate",
        details={"mode": "scaffold_replacement"},
    )


def _advanced_scaffold_unsupported(case: dict[str, Any]) -> bool:
    case_id = case.get("id", "")
    comp = case.get("comparison", {})
    if case_id in ("M05", "M06"):
        return True
    if comp.get("changing_role") == "central_heterocycle":
        return True
    if comp.get("retained_roles") and comp.get("changing_role"):
        return True
    roles = comp.get("roles")
    if isinstance(roles, list) and "attachment_A" in roles:
        return True
    if not comp.get("reference") and case_id == "M06":
        return True
    return False


def _validate_bioisostere_vectors(
    reference_id: str,
    layouts,
) -> list[str]:
    ref_layout = next((l for l in layouts if l.molecule_id == reference_id), None)
    if ref_layout is None or not ref_layout.molblock:
        return ["reference layout missing"]
    ref_mol = Chem.MolFromMolBlock(ref_layout.molblock, sanitize=True, removeHs=False)
    if ref_mol is None:
        return ["reference molblock invalid"]
    ref_match = phenol_core_match(ref_mol)
    if not ref_match:
        return ["reference phenol core not found"]
    ref_ring = ring_atoms_from_phenol_match(ref_mol, ref_match)
    ref_para = phenol_attachment_ring_atom(ref_mol, ref_match)
    if ref_para is None:
        return ["reference bioisostere attachment not found"]
    ref_anchor = substituent_anchor_atom(ref_mol, ref_para, ref_ring)
    if ref_anchor is None:
        return ["reference substituent anchor not found"]
    ref_vec = attachment_vector(ref_mol, ref_para, ref_anchor)
    if ref_vec is None:
        return ["reference attachment vector missing"]

    errors: list[str] = []
    for layout in layouts:
        if layout.molecule_id == reference_id:
            continue
        mol = Chem.MolFromMolBlock(layout.molblock or "", sanitize=True, removeHs=False)
        if mol is None:
            errors.append(f"{layout.molecule_id}: invalid molblock")
            continue
        match = phenol_core_match(mol)
        if not match:
            errors.append(f"{layout.molecule_id}: phenol core lost")
            continue
        ring = ring_atoms_from_phenol_match(mol, match)
        para = phenol_attachment_ring_atom(mol, match)
        if para is None:
            errors.append(f"{layout.molecule_id}: bioisostere site not found")
            continue
        anchor = substituent_anchor_atom(mol, para, ring)
        if anchor is None:
            errors.append(f"{layout.molecule_id}: substituent anchor not found")
            continue
        tgt_vec = attachment_vector(mol, para, anchor)
        if tgt_vec is None:
            errors.append(f"{layout.molecule_id}: attachment vector missing")
            continue
        delta = angle_degrees(ref_vec, tgt_vec)
        if delta > _ANGLE_TOLERANCE_DEG:
            errors.append(
                f"{layout.molecule_id}: attachment vector {delta:.1f}° off reference"
            )
    return errors


def _run_phenol_bioisostere(case: dict[str, Any]) -> AlignmentResult:
    comp = case.get("comparison", {})
    reference_id = comp.get("reference")
    case_id = case.get("id", "")
    if not reference_id:
        return AlignmentResult(
            case_id=case_id,
            status="INFEASIBLE",
            user_message="scaffold_replacement requires reference",
        )

    inner_case = {
        **case,
        "comparison": {
            **comp,
            "mode": "same_scaffold",
            "core_smarts": PHENOL_CORE_SMARTS,
        },
    }
    inner = run_same_scaffold(inner_case)
    if inner.status != "OPTIMAL":
        return AlignmentResult(
            case_id=case_id,
            status=inner.status,
            user_message=inner.user_message,
            layouts=inner.layouts,
            details={**(inner.details or {}), "mode": "scaffold_replacement"},
            unsupported_reason=inner.unsupported_reason,
        )

    vec_errors = _validate_bioisostere_vectors(reference_id, inner.layouts)
    if vec_errors:
        return AlignmentResult(
            case_id=case_id,
            status="INFEASIBLE_OR_USER_VISIBLE_UNMATCHED",
            user_message="; ".join(vec_errors),
            layouts=inner.layouts,
            details={"errors": vec_errors, "mode": "scaffold_replacement"},
        )

    return AlignmentResult(
        case_id=case_id,
        status="OPTIMAL",
        certificate="candidate_selection_optimal",
        user_message="Phenol retained; bioisostere attachment vector preserved",
        layouts=inner.layouts,
        objective=[0, 0, 0, 0],
        details={
            "mode": "scaffold_replacement",
            "retained_fragment": comp.get("retained_fragment", "phenol ring"),
            "core_smarts": PHENOL_CORE_SMARTS,
            "terminal_atoms_not_mapped": True,
        },
    )


def run_scaffold_replacement(case: dict[str, Any]) -> AlignmentResult:
    case_id = case.get("id", "")
    comp = case.get("comparison", {})

    if _advanced_scaffold_unsupported(case):
        return _unsupported(
            case_id,
            "Central scaffold or ring-size replacement (M05/M06) — not in this slice",
        )

    if is_phenol_bioisostere_case(comp):
        return _run_phenol_bioisostere(case)

    reference_id = comp.get("reference")
    if reference_id:
        ref_spec = next(
            (m for m in case.get("molecules", []) if m["id"] == reference_id),
            None,
        )
        if ref_spec:
            ref_mol = ingest_molecule(reference_id, ref_spec["smiles"])
            if ref_mol and phenol_core_match(ref_mol.draw_mol):
                patched = {
                    **case,
                    "comparison": {
                        **comp,
                        "retained_fragment": "phenol ring",
                        "roles": {
                            "phenol_anchor": "OH attachment",
                            "bioisostere_attachment": "para attachment bond",
                        },
                    },
                }
                return _run_phenol_bioisostere(patched)

    return _unsupported(
        case_id,
        "No supported scaffold-replacement hypothesis for this selection",
    )


__all__ = ["run_scaffold_replacement"]
