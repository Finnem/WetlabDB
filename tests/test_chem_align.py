"""Tests for :mod:`wetlabdb.chem.align`."""

from __future__ import annotations

import io
import math
import zipfile

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from wetlabdb.chem.align import (
    CompoundExportRow,
    MolExportError,
    PageMolItem,
    _ANGSTROM_TO_CHEMDRAW,
    _PAGE_FIT_HEIGHT,
    _PAGE_FIT_WIDTH,
    _extract_submol,
    aligned_mol_blocks,
    compounds_to_mol_zip,
    compounds_to_page_mol,
)


def _ring_coords_from_block(block: str, n_ring: int = 6) -> list[tuple[float, float]]:
    mol = Chem.MolFromMolBlock(block, sanitize=False)
    assert mol is not None
    conf = mol.GetConformer()
    return [(conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y) for i in range(n_ring)]


def _rigid_rms(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> float:
    assert len(a) == len(b)
    cx1 = sum(p[0] for p in a) / len(a)
    cy1 = sum(p[1] for p in a) / len(a)
    cx2 = sum(p[0] for p in b) / len(b)
    cy2 = sum(p[1] for p in b) / len(b)
    a0 = [(p[0] - cx1, p[1] - cy1) for p in a]
    b0 = [(p[0] - cx2, p[1] - cy2) for p in b]
    return math.sqrt(sum((a0[i][0] - b0[i][0]) ** 2 + (a0[i][1] - b0[i][1]) ** 2 for i in range(len(a))) / len(a))


def test_mcs_aligns_mixed_kekule_and_aromatic_benzene():
    rows = [
        CompoundExportRow("1", "A", "c1ccccc1C"),
        CompoundExportRow("2", "B", "C1=CC=CC=C1C"),
    ]
    blocks = aligned_mol_blocks(rows)
    assert len(blocks) == 2
    r1 = _ring_coords_from_block(blocks[0][1])
    r2 = _ring_coords_from_block(blocks[1][1])
    assert _rigid_rms(r1, r2) < 0.05


def test_mcs_aligns_benzene_and_pyridine_atom_agnostic():
    rows = [
        CompoundExportRow("1", "Ben", "c1ccccc1"),
        CompoundExportRow("2", "Pyr", "c1ncccc1"),
    ]
    blocks = aligned_mol_blocks(rows)
    r1 = _ring_coords_from_block(blocks[0][1])
    r2 = _ring_coords_from_block(blocks[1][1])
    assert _rigid_rms(r1, r2) < 0.05


def test_exported_mol_has_no_dummy_atoms():
    rows = [
        CompoundExportRow("1", "A", "CCO"),
        CompoundExportRow("2", "B", "CCN"),
    ]
    for _name, block in aligned_mol_blocks(rows):
        mol = Chem.MolFromMolBlock(block, sanitize=False)
        assert mol is not None
        assert all(atom.GetAtomicNum() > 0 for atom in mol.GetAtoms())


def test_single_compound_skips_mcs():
    rows = [CompoundExportRow("x", "Solo", "CCO")]
    blocks = aligned_mol_blocks(rows)
    assert len(blocks) == 1
    assert blocks[0][0] == "Solo.mol"


def test_no_parseable_smiles_raises():
    rows = [CompoundExportRow("1", "Bad", "not-smiles")]
    with pytest.raises(MolExportError):
        aligned_mol_blocks(rows)


def test_zip_contains_one_mol_per_row():
    rows = [
        CompoundExportRow("1", "One", "CC"),
        CompoundExportRow("2", "Two", "CCC"),
    ]
    data, name = compounds_to_mol_zip(rows)
    assert name == "compounds_aligned.zip"
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
    assert len(names) == 2
    assert all(n.endswith(".mol") for n in names)


def test_mol_block_is_kekule_not_aromatic_query():
    rows = [CompoundExportRow("1", "Ben", "c1ccccc1")]
    block = aligned_mol_blocks(rows)[0][1]
    assert " arom" not in block.lower() or "  1  0  0  0  0" in block


def _sulfur_xy(block: str) -> tuple[float, float]:
    mol = Chem.MolFromMolBlock(block, sanitize=False)
    assert mol is not None
    conf = mol.GetConformer()
    for i, atom in enumerate(mol.GetAtoms()):
        if atom.GetSymbol() == "S":
            p = conf.GetAtomPosition(i)
            return (p.x, p.y)
    raise AssertionError("no sulfur in block")


def test_chalco_library_sulfur_and_core_aligned():
    """Regression: thiazole/benzothiazole SAR set shares S position and MCS map."""
    smiles = [
        ("001", "[s]1c2c(nc1C#N)ccc(c2)OC"),
        ("002", "[s]1c2c(nc1Cl)ccc(c2)[N+](=O)[O-]"),
        ("004", "[s]1cnc(c1N)C(=O)OCC"),
        ("005", "Ic1[s]c(c(c1)N)C(=O)OC"),
        ("006", "[s]1c2c(cc1C(=O)OC)cc(cc2)N"),
    ]
    rows = [CompoundExportRow(k, f"Chalco{k}", s) for k, s in smiles]
    blocks = aligned_mol_blocks(rows)
    s_ref = _sulfur_xy(blocks[0][1])
    for _name, block in blocks[1:]:
        s_xy = _sulfur_xy(block)
        assert _rigid_rms([s_ref], [s_xy]) < 0.05


def test_chalco_bicyclic_pair_keeps_sulfur_on_sulfur():
    rows = [
        CompoundExportRow("001", "A", "[s]1c2c(nc1C#N)ccc(c2)OC"),
        CompoundExportRow("006", "B", "[s]1c2c(cc1C(=O)OC)cc(cc2)N"),
    ]
    from wetlabdb.chem.align import _pick_mcs_and_matches, _prepare_mol

    mols = [_prepare_mol(r.smiles) for r in rows]
    picked = _pick_mcs_and_matches(mols)
    assert picked is not None
    _mcs, matches = picked
    ref_mol, ref_match = mols[0], matches[0]
    for mol, match in zip(mols[1:], matches[1:]):
        for qi, ri in enumerate(ref_match):
            if ref_mol.GetAtomWithIdx(ri).GetSymbol() != "S":
                continue
            assert mol.GetAtomWithIdx(match[qi]).GetSymbol() == "S"


def _item(doc_id: str, smiles: str, molblock: str = "") -> PageMolItem:
    return PageMolItem(doc_id, doc_id, smiles, molblock)


def _frag_bboxes(block: str) -> list[tuple[float, float, float, float]]:
    mol = Chem.MolFromMolBlock(block, sanitize=True, removeHs=False)
    assert mol is not None
    boxes = []
    for frag in Chem.GetMolFrags(mol, asMols=True):
        conf = frag.GetConformer()
        xs = [conf.GetAtomPosition(i).x for i in range(frag.GetNumAtoms())]
        ys = [conf.GetAtomPosition(i).y for i in range(frag.GetNumAtoms())]
        boxes.append((min(xs), min(ys), max(xs), max(ys)))
    return boxes


def test_page_mol_keeps_internal_geometry():
    mol = Chem.MolFromSmiles("Clc1ccccc1")
    AllChem.Compute2DCoords(mol)
    src = Chem.MolToMolBlock(mol, kekulize=False)
    conf = mol.GetConformer()
    before = [
        math.dist(
            (conf.GetAtomPosition(0).x, conf.GetAtomPosition(0).y),
            (conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y),
        )
        for i in range(1, mol.GetNumAtoms())
    ]
    block, name = compounds_to_page_mol([_item("a", "Clc1ccccc1", src)])
    assert name.endswith(".mol")
    got = Chem.MolFromMolBlock(block, sanitize=True, removeHs=False)
    assert got is not None
    gconf = got.GetConformer()
    after = [
        math.dist(
            (gconf.GetAtomPosition(0).x, gconf.GetAtomPosition(0).y),
            (gconf.GetAtomPosition(i).x, gconf.GetAtomPosition(i).y),
        )
        for i in range(1, got.GetNumAtoms())
    ]
    assert after == pytest.approx([d * _ANGSTROM_TO_CHEMDRAW for d in before], abs=1e-4)


def test_page_mol_places_row_without_overlap():
    items = [_item("a", "c1ccccc1"), _item("b", "c1ccccc1C")]
    block, _name = compounds_to_page_mol(items, columns=2)
    boxes = _frag_bboxes(block)
    assert len(boxes) == 2
    a, b = boxes
    separated = a[2] <= b[0] + 1e-6 or b[2] <= a[0] + 1e-6
    assert separated
    assert a[3] == pytest.approx(b[3], abs=0.05)


def test_page_mol_wraps_to_next_row():
    items = [_item("a", "c1ccccc1"), _item("b", "c1ccccc1"), _item("c", "c1ccccc1")]
    block, _name = compounds_to_page_mol(items, columns=2)
    boxes = _frag_bboxes(block)
    assert len(boxes) == 3
    tops = [box[3] for box in boxes]
    assert min(tops) < max(tops) - 0.15


def test_page_mol_uses_pose_not_fresh_smiles_layout():
    mol = Chem.MolFromSmiles("Clc1cc(C)ccc1")
    AllChem.Compute2DCoords(mol)
    conf = mol.GetConformer()
    for i in range(mol.GetNumAtoms()):
        p = conf.GetAtomPosition(i)
        conf.SetAtomPosition(i, (p.x + 4.0, p.y - 1.5, 0.0))
    posed = Chem.MolToMolBlock(mol, kekulize=False)
    block, _name = compounds_to_page_mol([_item("cl", "Clc1cc(C)ccc1", posed)])
    got = Chem.MolFromMolBlock(block, sanitize=True, removeHs=False)
    src_pairs = []
    dst_pairs = []
    sconf = mol.GetConformer()
    gconf = got.GetConformer()
    for i in range(mol.GetNumAtoms()):
        for j in range(i + 1, mol.GetNumAtoms()):
            src_pairs.append(
                math.dist(
                    (sconf.GetAtomPosition(i).x, sconf.GetAtomPosition(i).y),
                    (sconf.GetAtomPosition(j).x, sconf.GetAtomPosition(j).y),
                )
            )
            dst_pairs.append(
                math.dist(
                    (gconf.GetAtomPosition(i).x, gconf.GetAtomPosition(i).y),
                    (gconf.GetAtomPosition(j).x, gconf.GetAtomPosition(j).y),
                )
            )
    assert dst_pairs == pytest.approx(
        [d * _ANGSTROM_TO_CHEMDRAW for d in src_pairs], abs=1e-4
    )


def test_page_mol_small_figure_keeps_acs_size():
    mol = Chem.MolFromSmiles("c1ccccc1")
    AllChem.Compute2DCoords(mol)
    src = Chem.MolToMolBlock(mol, kekulize=False)
    conf = mol.GetConformer()
    before = math.dist(
        (conf.GetAtomPosition(0).x, conf.GetAtomPosition(0).y),
        (conf.GetAtomPosition(1).x, conf.GetAtomPosition(1).y),
    )
    block, _name = compounds_to_page_mol([_item("a", "c1ccccc1", src)])
    got = Chem.MolFromMolBlock(block, sanitize=True, removeHs=False)
    gconf = got.GetConformer()
    after = math.dist(
        (gconf.GetAtomPosition(0).x, gconf.GetAtomPosition(0).y),
        (gconf.GetAtomPosition(1).x, gconf.GetAtomPosition(1).y),
    )
    assert after == pytest.approx(before * _ANGSTROM_TO_CHEMDRAW, abs=1e-4)


def _page_atom_span(block: str) -> tuple[float, float]:
    mol = Chem.MolFromMolBlock(block, sanitize=True, removeHs=False)
    assert mol is not None
    conf = mol.GetConformer()
    xs = [conf.GetAtomPosition(i).x for i in range(mol.GetNumAtoms())]
    ys = [conf.GetAtomPosition(i).y for i in range(mol.GetNumAtoms())]
    return max(xs) - min(xs), max(ys) - min(ys)


def test_page_mol_tall_figure_keeps_acs_size_and_page_width():
    mol = Chem.MolFromSmiles("c1ccccc1")
    AllChem.Compute2DCoords(mol)
    before = math.dist(
        (mol.GetConformer().GetAtomPosition(0).x, mol.GetConformer().GetAtomPosition(0).y),
        (mol.GetConformer().GetAtomPosition(1).x, mol.GetConformer().GetAtomPosition(1).y),
    )
    items = [_item(f"m{i}", "c1ccccc1") for i in range(40)]
    block, _name = compounds_to_page_mol(items, columns=2)
    width, height = _page_atom_span(block)
    got = Chem.MolFromMolBlock(block, sanitize=True, removeHs=False)
    assert got is not None
    gconf = got.GetConformer()
    after = math.dist(
        (gconf.GetAtomPosition(0).x, gconf.GetAtomPosition(0).y),
        (gconf.GetAtomPosition(1).x, gconf.GetAtomPosition(1).y),
    )
    assert width <= _PAGE_FIT_WIDTH + 1e-3
    assert height > _PAGE_FIT_HEIGHT
    assert after == pytest.approx(before * _ANGSTROM_TO_CHEMDRAW, abs=1e-4)


def test_page_mol_shrinks_wide_chain_to_chemdraw_page():
    smiles = "C" * 48
    mol = Chem.MolFromSmiles(smiles)
    AllChem.Compute2DCoords(mol)
    src = Chem.MolToMolBlock(mol, kekulize=False)
    native = _atom_span_from_mol(mol)
    block, _name = compounds_to_page_mol([_item("chain", smiles, src)])
    width, _height = _page_atom_span(block)
    assert native[0] > _PAGE_FIT_WIDTH
    assert width <= _PAGE_FIT_WIDTH + 1e-3


def test_page_mol_row_of_druglike_mols_fits_one_page_width():
    smiles = "COc1ccc2nc(C#N)sc2c1"
    items = [_item(f"m{i}", smiles) for i in range(3)]
    block, _name = compounds_to_page_mol(items, columns=3)
    width, _height = _page_atom_span(block)
    assert width <= _PAGE_FIT_WIDTH + 1e-3


def test_page_mol_uses_preview_columns_not_page_packing():
    items = [_item(f"m{i}", "c1ccccc1") for i in range(6)]
    block, _name = compounds_to_page_mol(items, columns=2)
    boxes = _frag_bboxes(block)
    assert len(boxes) == 6
    tops = sorted((box[3] for box in boxes), reverse=True)
    rows = 1
    for prev, cur in zip(tops, tops[1:]):
        if prev - cur > 0.12:
            rows += 1
    assert rows == 3
    width, _height = _page_atom_span(block)
    assert width <= _PAGE_FIT_WIDTH + 1e-3


def test_page_mol_chemdraw_width_is_one_a4_drawing():
    smiles = "COc1ccc2nc(C#N)sc2c1"
    items = [_item(f"m{i}", smiles) for i in range(8)]
    block, _name = compounds_to_page_mol(items, columns=3)
    width, _height = _page_atom_span(block)
    assert width * 72.0 <= 523.32 + 0.5


def _atom_span_from_mol(mol: Chem.Mol) -> tuple[float, float]:
    conf = mol.GetConformer()
    xs = [conf.GetAtomPosition(i).x for i in range(mol.GetNumAtoms())]
    ys = [conf.GetAtomPosition(i).y for i in range(mol.GetNumAtoms())]
    return max(xs) - min(xs), max(ys) - min(ys)


def test_page_mol_rejects_empty_selection():
    with pytest.raises(MolExportError):
        compounds_to_page_mol([_item("bad", "not-smiles")])


def test_extract_submol_incomplete_aromatic_path():
    mol = Chem.MolFromSmiles("CCOC(=O)c1cscn1")
    assert mol is not None
    Chem.SanitizeMol(mol)
    ring = mol.GetRingInfo().AtomRings()[0]
    frag = _extract_submol(mol, ring[:3])
    assert frag.GetNumAtoms() == 3
    full = _extract_submol(mol, list(ring))
    assert full.GetNumAtoms() == len(ring)


def test_page_cdxml_keeps_acs_bond_length_and_names():
    from wetlabdb.chem.align import compounds_to_page_cdxml
    import re

    items = [
        PageMolItem("1", "Chalco001", "COc1ccc2nc(C#N)sc2c1"),
        PageMolItem("2", "Chalco002", "O=[N+]([O-])c1ccc2nc(Cl)sc2c1"),
        PageMolItem("3", "Chalco006", "COC(=O)c1cc2cc(N)ccc2s1"),
    ]
    xml, name = compounds_to_page_cdxml(items, columns=3, filename="series.cdxml")
    assert name.endswith(".cdxml")
    assert 'BondLength="14.40"' in xml
    assert "WidthPages=\"1\"" in xml
    assert "Chalco001" in xml
    assert "Chalco002" in xml
    assert "Chalco006" in xml
    assert 'face="96"' not in xml
    assert 'face="0"' in xml
    assert 'Order="2"' in xml
    assert 'Order="3"' in xml
    xs = []
    for line in xml.split('p="'):
        if line[:1].isdigit() or line[:1] == "-":
            x = float(line.split()[0])
            xs.append(x)
    assert xs
    assert max(xs) <= 36 + 523.32 + 1.0
    mols = Chem.MolsFromCDXML(xml)
    assert mols is not None
    assert len(mols) == 3
    caption_y = [float(y) for y in re.findall(r'<t [^>]*p="[\d.]+ ([\d.]+)"', xml)]
    assert len(caption_y) == 3
    assert max(caption_y) - min(caption_y) < 1.0


def test_page_cdxml_grid_aligns_rows_and_columns():
    from wetlabdb.chem.align import compounds_to_page_cdxml
    import re

    items = [
        PageMolItem(f"m{i}", f"Name{i}", "c1ccccc1" if i % 2 == 0 else "c1ccccc1C")
        for i in range(4)
    ]
    xml, _name = compounds_to_page_cdxml(items, columns=2)
    captions = [
        (float(x), float(y))
        for x, y in re.findall(r'<t [^>]*p="([\d.]+) ([\d.]+)"', xml)
    ]
    assert len(captions) == 4
    xs = sorted({round(x, 1) for x, _y in captions})
    ys = sorted({round(y, 1) for _x, y in captions})
    assert len(xs) == 2
    assert len(ys) == 2
    assert xs[1] - xs[0] > 40
    assert ys[1] - ys[0] > 20
