"""Parity: CSV import/export matching csv_io + visible-column export."""

from __future__ import annotations

import io

import pandas as pd


def test_import_creates_and_updates(admin_client):
    csv_text = "Name,SMILES\nAspirin,new-smiles\nBrandNew,CC\n"
    files = {"file": ("in.csv", csv_text, "text/csv")}
    data = {"identifier_col": "Name", "data_cols": "SMILES", "on_collision": "overwrite"}
    response = admin_client.post(
        "/api/databases/WetlabDB/collections/Compounds/csv/import",
        files=files,
        data=data,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 1
    assert body["updated"] == 1

    listed = admin_client.get(
        "/api/databases/WetlabDB/collections/Compounds/compounds"
    ).json()["compounds"]
    by_name = {c["Name"]: c for c in listed}
    assert by_name["Aspirin"]["SMILES"] == "new-smiles"
    assert by_name["BrandNew"]["SMILES"] == "CC"


def test_import_append_keeps_existing_and_sets_alternative_name(admin_client):
    csv_text = "Name,SMILES\nAspirin,new-smiles\n"
    response = admin_client.post(
        "/api/databases/WetlabDB/collections/Compounds/csv/import",
        files={"file": ("in.csv", csv_text, "text/csv")},
        data={"identifier_col": "Name", "data_cols": "SMILES"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 0
    assert body["updated"] == 0
    assert body["appended"] == 1
    listed = admin_client.get(
        "/api/databases/WetlabDB/collections/Compounds/compounds"
    ).json()["compounds"]
    aspirin = next(c for c in listed if c["Name"] == "Aspirin")
    assert aspirin["SMILES"] != "new-smiles"
    assert aspirin["alternative SMILES"] == "new-smiles"


def test_import_skips_nan_identifier_and_preserves_nan_data(admin_client):
    seed = admin_client.post(
        "/api/databases/WetlabDB/collections/Compounds/compounds",
        json={"data": {"Name": "KeepPure", "Pure": True}},
    )
    assert seed.status_code == 201
    csv_text = "Name,Pure\nKeepPure,\n,\n"
    response = admin_client.post(
        "/api/databases/WetlabDB/collections/Compounds/csv/import",
        files={"file": ("in.csv", csv_text, "text/csv")},
        data={"identifier_col": "Name", "data_cols": "Pure", "on_collision": "overwrite"},
    )
    assert response.status_code == 200
    doc_id = seed.json()["_id"]
    fetched = admin_client.get(
        f"/api/databases/WetlabDB/collections/Compounds/compounds/{doc_id}"
    ).json()
    assert fetched["Pure"] is True


def test_export_uses_visible_columns_only(admin_client):
    response = admin_client.get(
        "/api/databases/WetlabDB/collections/Compounds/csv/export",
        params={"columns": "Name,SMILES"},
    )
    assert response.status_code == 200
    text = response.text
    header = text.splitlines()[0]
    assert header == "Name,SMILES"
    assert "LabNote" not in header
    assert "Aspirin" in text


def test_search_results_csv_includes_similarity(admin_client):
    response = admin_client.get(
        "/api/databases/WetlabDB/collections/Compounds/search/similarity.csv",
        params={
            "query": "CC(=O)OC1=CC=CC=C1C(=O)O",
            "cutoff": 0.5,
            "metric": "Tanimoto",
        },
    )
    assert response.status_code == 200
    df = pd.read_csv(io.StringIO(response.text))
    assert "Similarity" in df.columns
    assert "Aspirin" in set(df["Name"])
