"""Ring atom replacement alignment (Slice 4 / M02)."""

from __future__ import annotations

from typing import Any

from rdkit import Chem
from rdkit.Chem import AllChem, rdDepictor, rdFMCS

from wetlabdb.chem.align import _flatten_z, _init_rings
from wetlabdb.sar.pipeline.ingestion import IngestedMolecule, identity_unchanged, ingest_molecule
from wetlabdb.sar.pipeline.models import AlignmentResult, MoleculeLayout
from wetlabdb.sar.pipeline.ring_roles import (
    elements_compatible,
    exocyclic_pairs,
    pick_reference_ring,
    ring_attachment_roles,
    six_membered_aromatic_rings,
)

_MCS_KW = dict(
    bondCompare=rdFMCS.BondCompare.CompareOrder,
    ringMatchesRingOnly=True,
    timeout=30,
)


def _exocyclic_cl_atom(mol: Chem.Mol, ring_atom: int, ring_atoms: set[int]) -> int | None:
    for nbr in mol.GetAtomWithIdx(ring_atom).GetNeighbors():
        ni = nbr.GetIdx()
        if ni not in ring_atoms and nbr.GetAtomicNum() == 17:
            return ni
    return None


def _mcs_atom_pairs(ref_mol: Chem.Mol, tgt_mol: Chem.Mol) -> list[tuple[int, int]]:
    result = rdFMCS.FindMCS(
        [ref_mol, tgt_mol],
        atomCompare=rdFMCS.AtomCompare.CompareAnyHeavyAtom,
        **_MCS_KW,
    )
    if result.canceled or not result.smartsString:
        return []
    query = Chem.MolFromSmarts(result.smartsString)
    if query is None:
        return []
    ref_match = ref_mol.GetSubstructMatch(query)
    tgt_match = tgt_mol.GetSubstructMatch(query)
    if not ref_match or not tgt_match:
        return []
    return list(zip(ref_match, tgt_match))


def _find_target_mapping(
    ref_mol: Chem.Mol,
    ref_order: tuple[int, ...],
    ref_roles: dict[str, int | None],
    tgt_mol: Chem.Mol,
    *,
    allow_cn: bool,
) -> tuple[tuple[int, ...], list[tuple[int, int]]] | None:
    ref_ring_set = set(ref_order)
    ref_amino = ref_roles.get("amino_site")
    ref_chloro = ref_roles.get("chloro_site")
    if ref_amino is None or ref_chloro is None:
        return None

    for tgt_ring in six_membered_aromatic_rings(tgt_mol):
        tgt_set = set(tgt_ring)
        tgt_roles = ring_attachment_roles(tgt_mol, tgt_set)
        tgt_amino = tgt_roles.get("amino_site")
        tgt_chloro = tgt_roles.get("chloro_site")
        if tgt_amino is None or tgt_chloro is None:
            continue

        pair_map: dict[int, int] = {}
        used_tgt: set[int] = set()
        pair_map[ref_amino] = tgt_amino
        pair_map[ref_chloro] = tgt_chloro
        used_tgt.update((tgt_amino, tgt_chloro))
        ref_cl = _exocyclic_cl_atom(ref_mol, ref_chloro, ref_ring_set)
        tgt_cl = _exocyclic_cl_atom(tgt_mol, tgt_chloro, tgt_set)
        if ref_cl is not None and tgt_cl is not None:
            pair_map[ref_cl] = tgt_cl
            used_tgt.add(tgt_cl)

        mcs_pairs = _mcs_atom_pairs(ref_mol, tgt_mol)
        mcs_by_ref = {r: t for r, t in mcs_pairs}

        for ref_i, tgt_i in mcs_pairs:
            if ref_i in pair_map or tgt_i in used_tgt:
                continue
            if ref_i not in ref_ring_set or tgt_i not in tgt_set:
                continue
            if not elements_compatible(
                ref_mol, ref_i, tgt_mol, tgt_i, ref_roles, allow_cn=allow_cn
            ):
                continue
            pair_map[ref_i] = tgt_i
            used_tgt.add(tgt_i)

        for ri in ref_order:
            if ri in pair_map:
                continue
            hint = mcs_by_ref.get(ri)
            candidates = [
                t
                for t in tgt_set
                if t not in used_tgt
                and elements_compatible(ref_mol, ri, tgt_mol, t, ref_roles, allow_cn=allow_cn)
            ]
            if not candidates:
                break
            pick = hint if hint in candidates else candidates[0]
            pair_map[ri] = pick
            used_tgt.add(pick)
        else:
            if not all(ri in pair_map for ri in ref_order):
                continue
            if not all(
                elements_compatible(
                    ref_mol, ri, tgt_mol, pair_map[ri], ref_roles, allow_cn=allow_cn
                )
                for ri in ref_order
            ):
                continue
            if pair_map.get(ref_amino) != tgt_amino or pair_map.get(ref_chloro) != tgt_chloro:
                continue

            tgt_order = tuple(pair_map[ri] for ri in ref_order)
            atom_pairs: list[tuple[int, int]] = []
            seen: set[tuple[int, int]] = set()
            for ri in ref_order:
                ti = pair_map[ri]
                for pair in [
                    (ri, ti),
                    *exocyclic_pairs(ref_mol, ri, tgt_mol, ti, ref_ring_set, tgt_set),
                ]:
                    if pair not in seen:
                        seen.add(pair)
                        atom_pairs.append(pair)
            return tgt_order, atom_pairs
        continue
    return None


def _depict_matching(ref_mol: Chem.Mol, tgt_mol: Chem.Mol, atom_pairs: list[tuple[int, int]]) -> Chem.Mol:
    aligned = Chem.Mol(tgt_mol)
    _init_rings(aligned)
    _init_rings(ref_mol)
    if ref_mol.GetNumConformers() == 0:
        AllChem.Compute2DCoords(ref_mol)
    try:
        rdDepictor.GenerateDepictionMatching2DStructure(aligned, ref_mol, atom_pairs)
    except Exception:
        AllChem.Compute2DCoords(aligned)
    _flatten_z(aligned)
    return aligned


def run_ring_atom_replacements(case: dict[str, Any]) -> AlignmentResult:
    comp = case.get("comparison", {})
    case_id = case.get("id", "")
    reference_id = comp.get("reference")
    if not reference_id:
        return AlignmentResult(
            case_id=case_id,
            status="UNSUPPORTED",
            unsupported_reason="ring_atom_replacements requires reference",
        )

    allowed = comp.get("allowed_atom_changes") or []
    allow_cn = any("C" in s and "N" in s for s in allowed)

    ingested: list[IngestedMolecule] = []
    for spec in case.get("molecules", []):
        item = ingest_molecule(spec["id"], spec["smiles"])
        if item is None:
            return AlignmentResult(
                case_id=case_id,
                status="INFEASIBLE_OR_USER_VISIBLE_UNMATCHED",
                user_message=f"Unparseable: {spec['id']}",
            )
        ingested.append(item)

    by_id = {m.molecule_id: m for m in ingested}
    ref = by_id.get(reference_id)
    if ref is None:
        return AlignmentResult(case_id=case_id, status="INFEASIBLE", user_message="missing reference")

    picked = pick_reference_ring(ref.draw_mol)
    if picked is None:
        return AlignmentResult(
            case_id=case_id,
            status="INFEASIBLE_OR_USER_VISIBLE_UNMATCHED",
            user_message="reference ring roles not found",
        )
    ref_order, ref_roles = picked

    ref_template = Chem.Mol(ref.draw_mol)
    AllChem.Compute2DCoords(ref_template)
    _flatten_z(ref_template)

    layouts: list[MoleculeLayout] = []
    errors: list[str] = []

    for item in ingested:
        mapping = _find_target_mapping(
            ref.draw_mol,
            ref_order,
            ref_roles,
            item.draw_mol,
            allow_cn=allow_cn,
        )
        if mapping is None:
            errors.append(f"{item.molecule_id}: no ring role mapping")
            continue
        _tgt_order, atom_pairs = mapping
        aligned = _depict_matching(ref_template, item.draw_mol, atom_pairs)
        if not identity_unchanged(item.source_mol, aligned):
            errors.append(f"{item.molecule_id}: identity changed")
            continue
        layouts.append(
            MoleculeLayout(
                molecule_id=item.molecule_id,
                smiles=item.source_smiles,
                molblock=Chem.MolToMolBlock(aligned, kekulize=False),
                core_atom_indices=list(_tgt_order),
            )
        )

    if errors or len(layouts) != len(ingested):
        return AlignmentResult(
            case_id=case_id,
            status="INFEASIBLE_OR_USER_VISIBLE_UNMATCHED",
            user_message="; ".join(errors) if errors else "partial match",
            layouts=layouts,
            details={"errors": errors, "mode": "ring_atom_replacements"},
        )

    return AlignmentResult(
        case_id=case_id,
        status="OPTIMAL",
        certificate="candidate_selection_optimal",
        user_message="Ring atom correspondence preserved (C/N tolerant region)",
        layouts=layouts,
        objective=[0, 0, 0, 0],
        details={
            "mode": "ring_atom_replacements",
            "allowed_atom_changes": allowed,
            "reference_ring_atoms": len(ref_order),
        },
    )


__all__ = ["run_ring_atom_replacements"]
