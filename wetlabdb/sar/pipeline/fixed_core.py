"""Same-scaffold fixed-core alignment (reference coordinates)."""

from __future__ import annotations

from typing import Any, Callable

ProgressFn = Callable[[str, int, int], None]

from rdkit import Chem
from rdkit.Chem import AllChem, rdDepictor

from wetlabdb.chem.align import _depict_to_template, _extract_submol, _flatten_z, _init_rings, _rotate_flip_conformer
from wetlabdb.sar.hardening.completion import apply_policy, infeasible_in_template_set, optimal_complete
from wetlabdb.sar.pipeline.ingestion import IngestedMolecule, identity_unchanged, ingest_molecule
from wetlabdb.sar.pipeline.isomorphisms import (
    ScaffoldElementMode,
    normalize_scaffold_element_mode,
    pick_scaffold_matches,
)
from wetlabdb.sar.pipeline.models import AlignmentResult, MoleculeLayout

COORD_TOLERANCE = 0.001


def _align_to_reference_core(
    ingested: list[IngestedMolecule],
    reference_id: str,
    core_smarts: str,
    *,
    ignore_bond_order: bool = False,
    scaffold_element_mode: ScaffoldElementMode = "from_smarts",
    progress: ProgressFn | None = None,
) -> tuple[list[MoleculeLayout], list[str]]:
    """Align each molecule to reference core coordinates. Returns layouts and errors."""
    by_id = {m.molecule_id: m for m in ingested}
    ref = by_id.get(reference_id)
    if ref is None:
        return [], [f"missing reference {reference_id}"]

    core_query, match_by_id, pick_errors = pick_scaffold_matches(
        by_id,
        reference_id,
        core_smarts,
        scaffold_element_mode=scaffold_element_mode,
        ignore_bond_order=ignore_bond_order,
        progress=progress,
    )
    if core_query is None:
        return [], pick_errors or ["invalid core_smarts"]
    if not match_by_id:
        return [], pick_errors or ["invalid core_smarts"]

    ref_match = match_by_id.get(reference_id)
    if not ref_match:
        return [], [f"reference {reference_id} missing core"]

    template = _extract_submol(ref.draw_mol, ref_match)
    if template.GetNumConformers() == 0:
        AllChem.Compute2DCoords(template)
        _rotate_flip_conformer(template)
    _flatten_z(template)

    layouts: list[MoleculeLayout] = []
    errors: list[str] = []
    n = len(ingested)
    if progress:
        progress("layout", 0, n)

    for i, item in enumerate(ingested, 1):
        try:
            aligned = Chem.Mol(item.draw_mol)
            match = match_by_id.get(item.molecule_id)
            if not match:
                errors.append(f"{item.molecule_id}: core not found")
                continue
            atom_map = [(qi, match[qi]) for qi in range(len(match))]
            _depict_to_template(aligned, template, atom_map)
            if not identity_unchanged(item.source_mol, aligned):
                errors.append(f"{item.molecule_id}: identity changed during depiction")
                continue
            block = Chem.MolToMolBlock(aligned, kekulize=False)
            layouts.append(
                MoleculeLayout(
                    molecule_id=item.molecule_id,
                    smiles=item.source_smiles,
                    molblock=block,
                    core_atom_indices=list(match),
                )
            )
        finally:
            if progress:
                progress("layout", i, n)

    if not layouts:
        return [], errors

    ref_conf = template.GetConformer()
    for layout in layouts:
        mol = Chem.MolFromMolBlock(layout.molblock or "", sanitize=True, removeHs=False)
        if mol is None:
            errors.append(f"{layout.molecule_id}: invalid molblock")
            continue
        match = match_by_id.get(layout.molecule_id)
        if not match:
            errors.append(f"{layout.molecule_id}: core not found")
            continue
        for qi, atom_idx in enumerate(match):
            p = mol.GetConformer().GetAtomPosition(atom_idx)
            ref_p = ref_conf.GetAtomPosition(qi)
            dx = p.x - ref_p.x
            dy = p.y - ref_p.y
            if (dx * dx + dy * dy) ** 0.5 > COORD_TOLERANCE:
                errors.append(
                    f"{layout.molecule_id}: core atom {atom_idx} displaced from reference"
                )
                break

    return layouts, errors


def run_same_scaffold(case: dict[str, Any], progress: ProgressFn | None = None) -> AlignmentResult:
    comp = case.get("comparison", {})
    reference_id = comp.get("reference")
    core_smarts = comp.get("core_smarts")
    case_id = case.get("id", "")

    if not reference_id or not core_smarts:
        return AlignmentResult(
            case_id=case_id,
            status="UNSUPPORTED",
            unsupported_reason="same_scaffold requires reference and core_smarts",
        )

    ingested: list[IngestedMolecule] = []
    specs = list(case.get("molecules", []))
    n_specs = len(specs)
    if progress:
        progress("ingest", 0, n_specs)
    for i, spec in enumerate(specs, 1):
        item = ingest_molecule(spec["id"], spec["smiles"], spec.get("molblock"))
        if item is None:
            return AlignmentResult(
                case_id=case_id,
                status="INFEASIBLE_OR_USER_VISIBLE_UNMATCHED",
                user_message=f"Unparseable structure: {spec['id']}",
                details={"unmatched": [spec["id"]]},
            )
        ingested.append(item)
        if progress:
            progress("ingest", i, n_specs)

    scaffold_element_mode: ScaffoldElementMode = normalize_scaffold_element_mode(
        str(comp.get("scaffold_element_mode") or "")
    )

    layouts, errors = _align_to_reference_core(
        ingested,
        reference_id,
        core_smarts,
        ignore_bond_order=bool(comp.get("ignore_bond_order")),
        scaffold_element_mode=scaffold_element_mode,
        progress=progress,
    )
    if errors:
        base = AlignmentResult(
            case_id=case_id,
            status="INFEASIBLE_OR_USER_VISIBLE_UNMATCHED",
            user_message="; ".join(errors),
            layouts=layouts,
            details={"errors": errors, "unmatched": [e.split(":")[0] for e in errors if ":" in e]},
        )
        return apply_policy(base, infeasible_in_template_set())

    base = AlignmentResult(
        case_id=case_id,
        status="OPTIMAL",
        certificate="candidate_selection_optimal",
        user_message="Best layout proven within this template set",
        layouts=layouts,
        objective=[0, 0, 0, 0],
        details={
            "mode": "same_scaffold",
            "core_smarts": core_smarts,
            "ignore_bond_order": bool(comp.get("ignore_bond_order")),
            "scaffold_element_mode": scaffold_element_mode,
        },
    )
    return apply_policy(base, optimal_complete())


__all__ = ["run_same_scaffold", "COORD_TOLERANCE"]
