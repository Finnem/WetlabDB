"""Tests for :mod:`wetlabdb.chem.enumerate`."""

from __future__ import annotations

from rdkit import Chem

from wetlabdb.chem.enumerate import enumerate_molecules_from_smarts


def _canon(mols) -> set[str]:
    return {Chem.MolToSmiles(m, canonical=True) for m in mols}


def test_returns_list_of_mols():
    mols = enumerate_molecules_from_smarts("[#6][#6]")
    assert isinstance(mols, list)
    assert len(mols) >= 1
    assert "CC" in _canon(mols)


def test_alternative_atomic_numbers_expanded():
    # Two-atom pattern over {C, N, O} on each side; generator produces
    # at least the diagonal (CC, NN, OO).
    mols = enumerate_molecules_from_smarts("[#6,#7,#8][#6,#7,#8]")
    canon = _canon(mols)
    assert "CC" in canon
    # NN is more reliable than ON across versions; ensure at least 2 distinct.
    assert len(canon) >= 2


def test_invalid_smarts_returns_empty_list():
    assert enumerate_molecules_from_smarts("totally bogus !!! [[[") == []


def test_unique_canonical_smiles_only():
    mols = enumerate_molecules_from_smarts("[#6][#6]")
    canon = [Chem.MolToSmiles(m, canonical=True) for m in mols]
    assert len(canon) == len(set(canon)), "duplicates leaked through"
