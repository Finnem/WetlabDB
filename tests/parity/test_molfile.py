"""Parity: Ketcher molfile is converted to aromatic storage SMILES."""

from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import AllChem


def test_from_molfile_kekule_benzene(admin_client):
    mol = Chem.MolFromSmiles("c1ccccc1")
    AllChem.Compute2DCoords(mol)
    Chem.Kekulize(mol)
    molfile = Chem.MolToMolBlock(mol)
    response = admin_client.post("/api/chem/from-molfile", json={"molfile": molfile})
    assert response.status_code == 200
    assert response.json()["smiles"] == "c1ccccc1"
