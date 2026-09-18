"""Ketcher-like molfile → storage-string contract."""

from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import AllChem

from wetlabdb.chem.smiles import molfile_to_storage_string


def _kekule_molfile(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None
    AllChem.Compute2DCoords(mol)
    Chem.Kekulize(mol)
    return Chem.MolToMolBlock(mol)


def test_ketcher_kekule_benzene_molfile_stores_aromatic_smiles():
    molfile = _kekule_molfile("c1ccccc1")
    assert "=" in molfile or "  2  " in molfile
    stored = molfile_to_storage_string(molfile)
    assert stored == "c1ccccc1"


def test_ketcher_kekule_phenol_molfile_stays_aromatic():
    stored = molfile_to_storage_string(_kekule_molfile("Oc1ccccc1"))
    assert stored is not None
    assert "c1" in stored or "c1ccccc1" in Chem.MolToSmiles(Chem.MolFromSmiles(stored))
    mol = Chem.MolFromSmiles(stored)
    assert mol is not None
    assert mol.GetAtomWithIdx(0).GetIsAromatic() or any(
        a.GetIsAromatic() for a in mol.GetAtoms()
    )


def test_empty_molfile_returns_none():
    assert molfile_to_storage_string("") is None
    assert molfile_to_storage_string("not a molfile") is None
