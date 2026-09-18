"""Parity: aligned MOL ZIP export."""

from __future__ import annotations

import io
import zipfile


def _add(admin_client, name: str, smiles: str) -> str:
    r = admin_client.post(
        "/api/databases/WetlabDB/collections/Compounds/compounds",
        json={"data": {"Name": name, "SMILES": smiles}},
    )
    assert r.status_code == 201, r.text
    return r.json()["_id"]


def test_mol_export_zip_only_requested_ids(admin_client):
    id_a = _add(admin_client, "MolExpA", "CCO")
    id_b = _add(admin_client, "MolExpB", "CCN")
    _add(admin_client, "MolExpSkip", "CCC")

    response = admin_client.post(
        "/api/databases/WetlabDB/collections/Compounds/mol/export",
        json={"ids": [id_a, id_b]},
    )
    assert response.status_code == 200, response.text
    assert "application/zip" in response.headers.get("content-type", "")
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        names = zf.namelist()
    assert len(names) == 2
    assert any("MolExpA" in n for n in names)
    assert any("MolExpB" in n for n in names)
    assert not any("MolExpSkip" in n for n in names)


def test_mol_export_empty_ids_rejected(admin_client):
    response = admin_client.post(
        "/api/databases/WetlabDB/collections/Compounds/mol/export",
        json={"ids": []},
    )
    assert response.status_code == 422


def test_mol_export_unparseable_smiles_400(admin_client):
    doc_id = _add(admin_client, "MolBad", "???")
    response = admin_client.post(
        "/api/databases/WetlabDB/collections/Compounds/mol/export",
        json={"ids": [doc_id]},
    )
    assert response.status_code == 400
