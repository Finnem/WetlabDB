"""Parity: compound CRUD, extra keys, text filter, PNG render, schema."""

from __future__ import annotations

from wetlabdb.schema.compound import COMPOUND_FORM, default_compound_document


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def test_schema_matches_compound_form(admin_client):
    body = admin_client.get("/api/schema/compound").json()
    assert body["fields"] == COMPOUND_FORM
    assert body["defaults"] == default_compound_document()
    assert set(body["defaults"]) == set(COMPOUND_FORM)


def test_list_returns_seeded_docs_with_string_ids(admin_client):
    body = admin_client.get(
        "/api/databases/WetlabDB/collections/Compounds/compounds"
    ).json()
    compounds = body["compounds"]
    names = {c["Name"] for c in compounds}
    assert {"Aspirin", "Caffeine", "Toluene", "Extra"} <= names
    for doc in compounds:
        assert isinstance(doc["_id"], str)


def test_add_default_form_keys_round_trip(admin_client):
    payload = default_compound_document()
    payload["Name"] = "NewOne"
    payload["SMILES"] = "C"
    created = admin_client.post(
        "/api/databases/WetlabDB/collections/Compounds/compounds",
        json={"data": payload},
    )
    assert created.status_code == 201
    doc = created.json()
    assert doc["Name"] == "NewOne"
    fetched = admin_client.get(
        f"/api/databases/WetlabDB/collections/Compounds/compounds/{doc['_id']}"
    )
    assert fetched.status_code == 200
    assert fetched.json()["SMILES"] == "C"


def test_update_unset_and_delete(admin_client):
    created = admin_client.post(
        "/api/databases/WetlabDB/collections/Compounds/compounds",
        json={"data": {"Name": "Temp", "SMILES": "CC", "Scratch": "yes"}},
    )
    doc_id = created.json()["_id"]
    updated = admin_client.put(
        f"/api/databases/WetlabDB/collections/Compounds/compounds/{doc_id}",
        json={"data": {"Name": "Temp2"}, "unset": ["Scratch"]},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["Name"] == "Temp2"
    assert "Scratch" not in body
    deleted = admin_client.delete(
        f"/api/databases/WetlabDB/collections/Compounds/compounds/{doc_id}"
    )
    assert deleted.status_code == 200
    missing = admin_client.get(
        f"/api/databases/WetlabDB/collections/Compounds/compounds/{doc_id}"
    )
    assert missing.status_code == 404


def test_extra_keys_round_trip(admin_client):
    listed = admin_client.get(
        "/api/databases/WetlabDB/collections/Compounds/compounds"
    ).json()["compounds"]
    extra = next(c for c in listed if c["Name"] == "Extra")
    assert extra["LabNote"] == "dynamic-field"


def test_text_filter_all_columns(admin_client):
    body = admin_client.get(
        "/api/databases/WetlabDB/collections/Compounds/compounds",
        params={"q": "aspirin", "column": "All"},
    ).json()
    names = {c["Name"] for c in body["compounds"]}
    assert names == {"Aspirin"}


def test_text_filter_specific_column(admin_client):
    hits = admin_client.get(
        "/api/databases/WetlabDB/collections/Compounds/compounds",
        params={"q": "50-78-2", "column": "CAS Nr"},
    ).json()["compounds"]
    assert [c["Name"] for c in hits] == ["Aspirin"]
    missed = admin_client.get(
        "/api/databases/WetlabDB/collections/Compounds/compounds",
        params={"q": "50-78-2", "column": "Name"},
    ).json()["compounds"]
    assert missed == []


def test_render_png_valid_smiles(admin_client):
    response = admin_client.get("/api/render.png", params={"smiles": "CCO"})
    assert response.status_code == 200
    assert response.content.startswith(PNG_SIGNATURE)
    assert response.headers["content-type"].startswith("image/png")


def test_render_png_invalid_smiles(admin_client):
    response = admin_client.get("/api/render.png", params={"smiles": "not-a-molecule"})
    assert response.status_code in {404, 422}


def test_chem_3d_mol_valid_smiles(admin_client):
    response = admin_client.get("/api/chem/3d.mol", params={"smiles": "CCO"})
    assert response.status_code == 200
    text = response.text
    assert "M  END" in text
    assert response.headers["content-type"].startswith("chemical/x-mdl-molfile")


def test_chem_3d_mol_invalid_smiles(admin_client):
    response = admin_client.get("/api/chem/3d.mol", params={"smiles": "not-a-molecule"})
    assert response.status_code == 404
