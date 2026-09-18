"""2D-align compounds to a shared MCS template and export Kekulé MOL blocks."""

from __future__ import annotations

import io
import math
import re
import zipfile
from dataclasses import dataclass
from typing import Iterable, Sequence

from rdkit import Chem
from rdkit.Chem import AllChem, rdDepictor, rdFMCS

from wetlabdb.chem.smiles import _safe_kekulize, parse_smiles, perceive_aromaticity

_MCS_BOND_KW = dict(
    bondCompare=rdFMCS.BondCompare.CompareOrder,
    ringMatchesRingOnly=True,
    timeout=30,
)

# Halogens + sulfur: must not swap with carbon in ambiguous MCS matches (N/O may differ).
_ANCHOR_ATOMIC_NUMS = frozenset({9, 16, 17, 35, 53})


class MolExportError(ValueError):
    """Raised when no exportable structures are available."""


@dataclass(frozen=True)
class CompoundExportRow:
    doc_id: str
    name: str
    smiles: str


def _prepare_mol(smiles: str) -> Chem.Mol | None:
    mol = parse_smiles(smiles)
    if mol is None:
        return None
    perceive_aromaticity(mol)
    return mol


def _run_find_mcs(
    mols: Sequence[Chem.Mol],
    *,
    atom_compare: rdFMCS.AtomCompare,
    complete_rings_only: bool,
) -> Chem.Mol | None:
    result = rdFMCS.FindMCS(
        mols,
        completeRingsOnly=complete_rings_only,
        atomCompare=atom_compare,
        **_MCS_BOND_KW,
    )
    if result.canceled or not result.smartsString:
        return None
    return Chem.MolFromSmarts(result.smartsString)


def _mcs_candidates(mols: Sequence[Chem.Mol]) -> list[Chem.Mol]:
    """MCS queries largest-first; topology-first then element-strict."""
    seen: set[str] = set()
    found: list[tuple[int, Chem.Mol]] = []
    modes = (
        (rdFMCS.AtomCompare.CompareAnyHeavyAtom, True),
        (rdFMCS.AtomCompare.CompareAnyHeavyAtom, False),
        (rdFMCS.AtomCompare.CompareElements, True),
        (rdFMCS.AtomCompare.CompareElements, False),
    )
    for atom_compare, complete_rings in modes:
        mcs = _run_find_mcs(
            mols, atom_compare=atom_compare, complete_rings_only=complete_rings
        )
        if mcs is None or mcs.GetNumAtoms() == 0:
            continue
        smarts = Chem.MolToSmarts(mcs)
        if smarts in seen:
            continue
        seen.add(smarts)
        found.append((mcs.GetNumAtoms(), mcs))
    found.sort(key=lambda x: -x[0])
    return [m for _, m in found]


def _match_element_score(
    ref_mol: Chem.Mol,
    ref_match: Sequence[int],
    mol: Chem.Mol,
    match: Sequence[int],
) -> int:
    return sum(
        1
        for qi, ri in enumerate(ref_match)
        if ref_mol.GetAtomWithIdx(ri).GetAtomicNum()
        == mol.GetAtomWithIdx(match[qi]).GetAtomicNum()
    )


def _match_respects_anchors(
    ref_mol: Chem.Mol,
    ref_match: Sequence[int],
    mol: Chem.Mol,
    match: Sequence[int],
) -> bool:
    for qi, ri in enumerate(ref_match):
        r_z = ref_mol.GetAtomWithIdx(ri).GetAtomicNum()
        if r_z not in _ANCHOR_ATOMIC_NUMS:
            continue
        if mol.GetAtomWithIdx(match[qi]).GetAtomicNum() != r_z:
            return False
    return True


def _pick_substruct_match(
    mol: Chem.Mol,
    mcs: Chem.Mol,
    ref_mol: Chem.Mol,
    ref_match: Sequence[int],
) -> tuple[int, ...]:
    matches = mol.GetSubstructMatches(mcs, uniquify=True)
    if not matches:
        return ()
    if not ref_match:
        return matches[0]
    best: tuple[int, ...] | None = None
    best_score = -1
    for candidate in matches:
        if not _match_respects_anchors(ref_mol, ref_match, mol, candidate):
            continue
        score = _match_element_score(ref_mol, ref_match, mol, candidate)
        if score > best_score:
            best_score = score
            best = candidate
    return best or ()


def _pick_mcs_and_matches(
    mols: Sequence[Chem.Mol],
) -> tuple[Chem.Mol, list[tuple[int, ...]]] | None:
    """Largest MCS with anchor-respecting matches on every structure."""
    for mcs in _mcs_candidates(mols):
        ref_match = mols[0].GetSubstructMatch(mcs)
        if not ref_match:
            continue
        matches: list[tuple[int, ...]] = []
        ok = True
        for mol in mols:
            picked = _pick_substruct_match(mol, mcs, mols[0], ref_match)
            if not picked:
                ok = False
                break
            matches.append(picked)
        if not ok or mcs.GetNumAtoms() < 5:
            continue
        try:
            _extract_submol(mols[0], matches[0])
        except Exception:
            continue
        return mcs, matches
    return None


def _init_rings(mol: Chem.Mol) -> None:
    try:
        mol.UpdatePropertyCache(strict=False)
        Chem.GetSSSR(mol)
    except Exception:
        pass


def _extract_submol(parent: Chem.Mol, atom_indices: Sequence[int]) -> Chem.Mol:
    """Copy induced subgraph from ``parent`` as a concrete (non-query) mol."""
    idx_set = set(atom_indices)
    rw = Chem.RWMol()
    old_to_new: dict[int, int] = {}
    for old_idx in atom_indices:
        atom = parent.GetAtomWithIdx(old_idx)
        new_atom = Chem.Atom(atom.GetAtomicNum())
        new_atom.SetFormalCharge(atom.GetFormalCharge())
        new_atom.SetIsAromatic(False)
        old_to_new[old_idx] = rw.AddAtom(new_atom)
    for bond in parent.GetBonds():
        a1, a2 = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        if a1 in idx_set and a2 in idx_set:
            rw.AddBond(old_to_new[a1], old_to_new[a2], bond.GetBondType())
    out = rw.GetMol()
    Chem.SanitizeMol(out)
    _init_rings(out)
    return out


def _flatten_z(mol: Chem.Mol) -> None:
    if mol.GetNumConformers() == 0:
        return
    conf = mol.GetConformer()
    for i in range(mol.GetNumAtoms()):
        p = conf.GetAtomPosition(i)
        conf.SetAtomPosition(i, (p.x, p.y, 0.0))


def _rotate_flip_conformer(mol: Chem.Mol) -> None:
    """Canonical 2D pose: long axis horizontal; heteroatoms biased to +x."""
    if mol.GetNumConformers() == 0 or mol.GetNumAtoms() == 0:
        return
    conf = mol.GetConformer()
    xs: list[float] = []
    ys: list[float] = []
    for i in range(mol.GetNumAtoms()):
        p = conf.GetAtomPosition(i)
        xs.append(p.x)
        ys.append(p.y)
    n = len(xs)
    cx = sum(xs) / n
    cy = sum(ys) / n
    xx = sum((x - cx) ** 2 for x in xs) / n
    yy = sum((y - cy) ** 2 for y in ys) / n
    xy = sum((xs[i] - cx) * (ys[i] - cy) for i in range(n)) / n
    # Principal axis angle (2x2 covariance).
    angle = 0.5 * math.atan2(2 * xy, xx - yy)
    cos_a = math.cos(-angle)
    sin_a = math.sin(-angle)
    for i in range(mol.GetNumAtoms()):
        x = xs[i] - cx
        y = ys[i] - cy
        xr = x * cos_a - y * sin_a
        yr = x * sin_a + y * cos_a
        conf.SetAtomPosition(i, (xr, yr, 0.0))

    hetero_x: list[float] = []
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() != 6:
            p = conf.GetAtomPosition(atom.GetIdx())
            hetero_x.append(p.x)
    if hetero_x and sum(hetero_x) / len(hetero_x) < 0:
        for i in range(mol.GetNumAtoms()):
            p = conf.GetAtomPosition(i)
            conf.SetAtomPosition(i, (-p.x, p.y, 0.0))


def _depict_to_template(
    mol: Chem.Mol,
    template: Chem.Mol,
    atom_map: Sequence[tuple[int, int]],
) -> None:
    """Align ``mol`` to ``template`` using explicit MCS atom pairs."""
    _init_rings(mol)
    _init_rings(template)
    if not atom_map:
        AllChem.Compute2DCoords(mol)
        _flatten_z(mol)
        return
    try:
        rdDepictor.GenerateDepictionMatching2DStructure(mol, template, atom_map)
    except Exception:
        AllChem.Compute2DCoords(mol)
    _flatten_z(mol)


def _mol_to_kekule_block(mol: Chem.Mol, name: str) -> str:
    work = Chem.Mol(mol)
    work.SetProp("_Name", name)
    _safe_kekulize(work)
    block = Chem.MolToMolBlock(work, kekulize=False)
    if not block.endswith("\n"):
        block += "\n"
    return block


def _sanitize_filename(name: str, fallback: str) -> str:
    base = (name or "").strip() or fallback
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base)
    base = base.strip(". ") or fallback
    return base[:200]


def aligned_mol_blocks(
    rows: Sequence[CompoundExportRow],
) -> list[tuple[str, str]]:
    """Return ``(zip_entry_name, mol_block)`` pairs in input order."""
    parsed: list[tuple[CompoundExportRow, Chem.Mol]] = []
    for row in rows:
        mol = _prepare_mol(row.smiles)
        if mol is not None:
            parsed.append((row, mol))

    if not parsed:
        raise MolExportError("No parseable SMILES in selection")

    if len(parsed) == 1:
        row, mol = parsed[0]
        AllChem.Compute2DCoords(mol)
        _flatten_z(mol)
        label = _sanitize_filename(row.name, row.doc_id)
        return [(f"{label}.mol", _mol_to_kekule_block(mol, label))]

    mols = [m for _, m in parsed]
    picked = _pick_mcs_and_matches(mols)
    if picked is None:
        # Fallback: independent 2D layouts (still Kekulé MOL).
        out: list[tuple[str, str]] = []
        used: dict[str, int] = {}
        for row, mol in parsed:
            AllChem.Compute2DCoords(mol)
            _flatten_z(mol)
            label = _sanitize_filename(row.name, row.doc_id)
            key = label.lower()
            used[key] = used.get(key, 0) + 1
            suffix = f"_{used[key]}" if used[key] > 1 else ""
            out.append((f"{label}{suffix}.mol", _mol_to_kekule_block(mol, label)))
        return out

    _mcs, matches = picked
    match0 = matches[0]
    template = _extract_submol(mols[0], match0)
    AllChem.Compute2DCoords(template)
    _rotate_flip_conformer(template)
    out_blocks: list[tuple[str, str]] = []
    used_names: dict[str, int] = {}
    for idx, (row, mol) in enumerate(parsed):
        aligned = Chem.Mol(mol)
        match = matches[idx]
        atom_map = [(qi, match[qi]) for qi in range(len(match))]
        _depict_to_template(aligned, template, atom_map)
        label = _sanitize_filename(row.name, row.doc_id)
        key = label.lower()
        used_names[key] = used_names.get(key, 0) + 1
        suffix = f"_{used_names[key]}" if used_names[key] > 1 else ""
        out_blocks.append(
            (f"{label}{suffix}.mol", _mol_to_kekule_block(aligned, label))
        )
    return out_blocks


def compounds_to_mol_zip(
    rows: Sequence[CompoundExportRow],
    *,
    archive_name: str = "compounds_aligned.zip",
) -> tuple[bytes, str]:
    """Build a ZIP of aligned MOL files. Returns ``(zip_bytes, archive_name)``."""
    blocks = aligned_mol_blocks(rows)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for entry_name, mol_block in blocks:
            zf.writestr(entry_name, mol_block)
    return buf.getvalue(), archive_name


def rows_from_docs(docs: Iterable[dict]) -> list[CompoundExportRow]:
    out: list[CompoundExportRow] = []
    for doc in docs:
        doc_id = str(doc.get("_id", ""))
        name = str(doc.get("Name") or doc_id)
        smiles = str(doc.get("SMILES") or "")
        out.append(CompoundExportRow(doc_id=doc_id, name=name, smiles=smiles))
    return out


__all__ = [
    "CompoundExportRow",
    "MolExportError",
    "aligned_mol_blocks",
    "compounds_to_mol_zip",
    "rows_from_docs",
]
