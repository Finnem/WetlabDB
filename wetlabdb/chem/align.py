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
    try:
        Chem.SanitizeMol(out)
    except Exception:
        for atom in out.GetAtoms():
            atom.SetIsAromatic(False)
        for bond in out.GetBonds():
            bond.SetIsAromatic(False)
            if bond.GetBondType() == Chem.BondType.AROMATIC:
                bond.SetBondType(Chem.BondType.SINGLE)
        try:
            Chem.SanitizeMol(out)
        except Exception:
            pass
    _init_rings(out)
    if parent.GetNumConformers():
        src = parent.GetConformer()
        conf = Chem.Conformer(out.GetNumAtoms())
        for old_idx, new_idx in old_to_new.items():
            conf.SetAtomPosition(new_idx, src.GetAtomPosition(old_idx))
        out.RemoveAllConformers()
        out.AddConformer(conf, assignId=True)
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


@dataclass(frozen=True)
class PageMolItem:
    doc_id: str
    name: str
    smiles: str
    molblock: str = ""


# ChemDraw ACS-1996 "fixed length" is 0.2 in = 14.4 pt. Documents store
# coordinates in inches even when the ruler is labelled in pt. Packing as if
# 1 unit were 1 cm left bonds at 0.508 in (2.5× ACS) so three druglike mols
# crossed the 523.32 pt page edge.
_ACS_BOND_PT = 14.4
_ACS_BOND_IN = _ACS_BOND_PT / 72.0
_RDKIT_BOND_ANGSTROM = 1.5
_PT_PER_IN = 72.0
_ANGSTROM_TO_CHEMDRAW = _ACS_BOND_IN / _RDKIT_BOND_ANGSTROM
_PAGE_DRAW_PT_W = 523.32
_PAGE_DRAW_PT_H = 769.92
_PAGE_GAP_X = 21.6 / _PT_PER_IN
_PAGE_GAP_Y = 14.4 / _PT_PER_IN
_PAGE_FIT_WIDTH = _PAGE_DRAW_PT_W / _PT_PER_IN
_PAGE_FIT_HEIGHT = _PAGE_DRAW_PT_H / _PT_PER_IN
_PAGE_FIT_PAD = 10.0 / _PT_PER_IN
_PAGE_FIT_SAFETY = 0.92
_PAGE_MAX_ROW_WIDTH = _PAGE_FIT_WIDTH


def _parse_export_molblock(text: str) -> Chem.Mol | None:
    """Parse a 2D molblock without stripping the empty name line."""
    if not text or not str(text).strip():
        return None
    raw = str(text).replace("\r\n", "\n")
    candidates = [raw]
    stripped = raw.strip("\n")
    if not raw.startswith("\n"):
        candidates.append("\n" + stripped)
    for block in candidates:
        try:
            mol = Chem.MolFromMolBlock(block, sanitize=True, removeHs=False)
        except Exception:
            mol = None
        if mol is not None and mol.GetNumConformers() > 0:
            return mol
    return None


def _mol_for_page(item: PageMolItem) -> Chem.Mol | None:
    posed = _parse_export_molblock(item.molblock)
    if posed is not None:
        _flatten_z(posed)
        return posed
    mol = _prepare_mol(item.smiles)
    if mol is None:
        return None
    AllChem.Compute2DCoords(mol)
    _flatten_z(mol)
    return mol


def _atom_bbox(mol: Chem.Mol) -> tuple[float, float, float, float]:
    conf = mol.GetConformer()
    xs = [conf.GetAtomPosition(i).x for i in range(mol.GetNumAtoms())]
    ys = [conf.GetAtomPosition(i).y for i in range(mol.GetNumAtoms())]
    return min(xs), min(ys), max(xs), max(ys)


def _translate_xy(mol: Chem.Mol, dx: float, dy: float) -> None:
    conf = mol.GetConformer()
    for i in range(mol.GetNumAtoms()):
        point = conf.GetAtomPosition(i)
        conf.SetAtomPosition(i, (point.x + dx, point.y + dy, 0.0))


def _scale_xy(mol: Chem.Mol, factor: float) -> None:
    if factor == 1.0:
        return
    conf = mol.GetConformer()
    for i in range(mol.GetNumAtoms()):
        point = conf.GetAtomPosition(i)
        conf.SetAtomPosition(i, (point.x * factor, point.y * factor, 0.0))


def _mols_bbox(mols: Sequence[Chem.Mol]) -> tuple[float, float, float, float]:
    boxes = [_atom_bbox(mol) for mol in mols if mol.GetNumAtoms()]
    if not boxes:
        return 0.0, 0.0, 0.0, 0.0
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _page_fit_scale(mols: Sequence[Chem.Mol]) -> float:
    """Shrink only when the packed figure is wider than one ChemDraw page.

    Height may run onto further pages. Never scale up: a small figure keeps
    ACS-sized bonds.
    """
    min_x, _min_y, max_x, _max_y = _mols_bbox(mols)
    width = max(max_x - min_x + 2 * _PAGE_FIT_PAD, 1e-6)
    raw = min(1.0, _PAGE_FIT_WIDTH / width)
    if raw >= 1.0:
        return 1.0
    return raw * _PAGE_FIT_SAFETY


def _layout_page_mols(
    mols: Sequence[Chem.Mol],
    *,
    columns: int | None,
    gap_x: float = _PAGE_GAP_X,
    gap_y: float = _PAGE_GAP_Y,
    max_row_width: float = _PAGE_MAX_ROW_WIDTH,
    extra_height: float = 0.0,
) -> None:
    """Pack left-to-right, wrapping down (ChemDraw y-up).

    When the figure reports a column count, wrap on that count so ChemDraw
    matches the A4 preview. Otherwise wrap when the next structure would
    cross the drawing width. A row that is still too wide is shrunk later.
    """
    cursor_x = 0.0
    cursor_top = 0.0
    row_height = 0.0
    col = 0
    for index, mol in enumerate(mols):
        min_x, min_y, max_x, max_y = _atom_bbox(mol)
        width = max(max_x - min_x, 0.5)
        height = max(max_y - min_y, 0.5)
        wrap = False
        if index > 0:
            if columns and col >= columns:
                wrap = True
            elif cursor_x + width > max_row_width:
                wrap = True
        if wrap:
            cursor_x = 0.0
            cursor_top -= row_height + gap_y
            row_height = 0.0
            col = 0
        _translate_xy(mol, cursor_x - min_x, cursor_top - max_y)
        cursor_x += width + gap_x
        row_height = max(row_height, height + extra_height)
        col += 1


def _layout_page_grid(
    mols: Sequence[Chem.Mol],
    *,
    columns: int,
    gap_x: float,
    gap_y: float,
    page_width: float,
    label_pad: float,
    name_band: float,
) -> list[tuple[float, float, float]]:
    """Place mols on a regular grid (ChemDraw y-up).

    Structures are centered in equal-width cells and bottom-aligned in each
    row so captions share one baseline. Returns ``(caption_x, caption_y,
    cell_width)`` in the same coordinate system.
    """
    n = len(mols)
    cols = max(1, min(int(columns), n))
    boxes = [_atom_bbox(mol) for mol in mols]
    widths = [max(box[2] - box[0], 0.5) for box in boxes]
    heights = [max(box[3] - box[1], 0.5) for box in boxes]
    cell_w = max(widths)
    total_w = cols * cell_w + max(cols - 1, 0) * gap_x
    if total_w > page_width:
        factor = page_width / total_w
        for mol in mols:
            _scale_xy(mol, factor)
        boxes = [_atom_bbox(mol) for mol in mols]
        widths = [max(box[2] - box[0], 0.5) for box in boxes]
        heights = [max(box[3] - box[1], 0.5) for box in boxes]
        cell_w *= factor
        gap_x *= factor
        gap_y *= factor
        label_pad *= factor
        name_band *= factor

    captions: list[tuple[float, float, float]] = []
    n_rows = (n + cols - 1) // cols
    cursor_top = 0.0
    for row in range(n_rows):
        start = row * cols
        stop = min(start + cols, n)
        row_h = max(heights[start:stop])
        structure_bottom = cursor_top - row_h
        for col, index in enumerate(range(start, stop)):
            min_x, min_y, max_x, max_y = boxes[index]
            dest_left = col * (cell_w + gap_x) + (cell_w - widths[index]) / 2.0
            _translate_xy(mols[index], dest_left - min_x, structure_bottom - min_y)
            captions.append(
                (
                    col * (cell_w + gap_x) + cell_w / 2.0,
                    structure_bottom - label_pad,
                    cell_w,
                )
            )
        cursor_top = structure_bottom - label_pad - name_band - gap_y
    return captions


def compounds_to_page_mol(
    items: Sequence[PageMolItem],
    *,
    columns: int | None = None,
    filename: str = "figure.mol",
) -> tuple[str, str]:
    """One disconnected MOL with preview-style wrapping. Returns ``(block, filename)``."""
    mols: list[Chem.Mol] = []
    for item in items:
        mol = _mol_for_page(item)
        if mol is not None and mol.GetNumAtoms() > 0:
            mols.append(mol)
    if not mols:
        raise MolExportError("No parseable structures in selection")

    for mol in mols:
        _scale_xy(mol, _ANGSTROM_TO_CHEMDRAW)
    _layout_page_mols(mols, columns=columns)
    origin_x, origin_y, _, _ = _mols_bbox(mols)
    for mol in mols:
        _translate_xy(mol, -origin_x + _PAGE_FIT_PAD, -origin_y + _PAGE_FIT_PAD)
    factor = _page_fit_scale(mols)
    if factor < 1.0:
        origin_x, origin_y, _, _ = _mols_bbox(mols)
        for mol in mols:
            _translate_xy(mol, -origin_x, -origin_y)
            _scale_xy(mol, factor)
            _translate_xy(mol, _PAGE_FIT_PAD, _PAGE_FIT_PAD)
    combo = mols[0]
    for extra in mols[1:]:
        combo = Chem.CombineMols(combo, extra)

    base = filename[:-4] if filename.lower().endswith(".mol") else filename
    label = _sanitize_filename(base, "figure")
    out_name = f"{label}.mol"

    work = Chem.Mol(combo)
    work.SetProp("_Name", label)
    _safe_kekulize(work)
    force_v3000 = work.GetNumAtoms() > 999 or work.GetNumBonds() > 999
    block = Chem.MolToMolBlock(work, kekulize=False, forceV3000=force_v3000)
    if not block.endswith("\n"):
        block += "\n"
    return block, out_name


def _mean_bond_length(mol: Chem.Mol) -> float:
    from rdkit.Chem.Draw import rdMolDraw2D

    mean = float(rdMolDraw2D.MeanBondLength(mol) or _RDKIT_BOND_ANGSTROM)
    return mean if mean > 0 else _RDKIT_BOND_ANGSTROM


def _scale_mean_bond_to(mol: Chem.Mol, target: float) -> None:
    _scale_xy(mol, target / _mean_bond_length(mol))


def _load_page_mols(items: Sequence[PageMolItem]) -> list[tuple[Chem.Mol, str]]:
    pairs: list[tuple[Chem.Mol, str]] = []
    for item in items:
        mol = _mol_for_page(item)
        if mol is not None and mol.GetNumAtoms() > 0:
            label = (item.name or item.doc_id or "Untitled").strip() or "Untitled"
            pairs.append((mol, label))
    if not pairs:
        raise MolExportError("No parseable structures in selection")
    return pairs


def compounds_to_page_cdxml(
    items: Sequence[PageMolItem],
    *,
    columns: int | None = None,
    filename: str = "figure.cdxml",
) -> tuple[str, str]:
    """ACS-1996 CDXML page with captions. Returns ``(xml, filename)``."""
    from wetlabdb.chem.cdxml import mols_to_cdxml

    label_pad = 18.0
    caption_gap = 8.0
    caption_h = 12.0
    name_band = caption_gap + caption_h
    pairs = _load_page_mols(items)
    mols = [mol for mol, _name in pairs]
    names = [name for _mol, name in pairs]
    for mol in mols:
        _safe_kekulize(mol)
        _scale_mean_bond_to(mol, _ACS_BOND_PT)
    cols = max(1, min(columns or len(mols), len(mols)))
    captions = _layout_page_grid(
        mols,
        columns=cols,
        gap_x=21.6,
        gap_y=16.0,
        page_width=_PAGE_DRAW_PT_W,
        label_pad=label_pad,
        name_band=name_band,
    )
    origin_x, _origin_y, _, max_y = _mols_bbox(mols)
    for mol in mols:
        _translate_xy(mol, -origin_x, -max_y)
    captions = [(x - origin_x, y - max_y, w) for x, y, w in captions]
    xml = mols_to_cdxml(mols, names, captions=captions)
    base = filename
    for suffix in (".cdxml", ".cdx", ".mol"):
        if base.lower().endswith(suffix):
            base = base[: -len(suffix)]
            break
    return xml, f"{_sanitize_filename(base, 'figure')}.cdxml"


__all__ = [
    "CompoundExportRow",
    "MolExportError",
    "PageMolItem",
    "aligned_mol_blocks",
    "compounds_to_mol_zip",
    "compounds_to_page_cdxml",
    "compounds_to_page_mol",
    "rows_from_docs",
]
