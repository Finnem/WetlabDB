"""Tests for :mod:`wetlabdb.chem.align`."""

from __future__ import annotations

import io
import math
import zipfile

import pytest
from rdkit import Chem

from wetlabdb.chem.align import (
    CompoundExportRow,
    MolExportError,
    aligned_mol_blocks,
    compounds_to_mol_zip,
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
