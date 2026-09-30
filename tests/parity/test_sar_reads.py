"""Parity: SAR read API (projects, series, snapshot, auth)."""

from __future__ import annotations


def test_projects_requires_auth(raw_client):
    response = raw_client.get("/api/projects")
    assert response.status_code == 401


def test_list_projects_and_series(user_client):
    body = user_client.get("/api/projects").json()
    assert "WetlabDB" in {p["id"] for p in body["projects"]}

    series = user_client.get("/api/projects/WetlabDB/series").json()
    assert "Compounds" in {s["id"] for s in series["series"]}


def test_assay_fields(user_client):
    body = user_client.get("/api/sar/assay-fields").json()
    ids = {f["id"] for f in body["assay_fields"]}
    assert "Pure" in ids
    assert "Name" not in ids


def test_snapshot_with_selected_ids(user_client):
    listed = user_client.get(
        "/api/databases/WetlabDB/collections/Compounds/compounds"
    ).json()["compounds"]
    aspirin = next(c for c in listed if c["Name"] == "Aspirin")
    cid = aspirin["_id"]

    snap = user_client.get(
        "/api/projects/WetlabDB/series/Compounds",
        params={"assays": "Pure", "ids": cid},
    )
    assert snap.status_code == 200
    body = snap.json()
    assert body["source"]["system_id"] == "wetlabdb"
    assert body["series"]["project_id"] == "WetlabDB"
    assert len(body["compounds"]) == 1
    compound = body["compounds"][0]
    assert compound["id"] == cid
    assert compound["structure"]["format"] == "smiles"
    assert compound["structure"]["coordinates_2d_source"] is None
    assert compound["structure"]["value"] == aspirin["SMILES"]


def test_hidden_project_returns_404(user_client):
    response = user_client.get("/api/projects/wetlabdb_meta/series")
    assert response.status_code == 404


def test_alignment_run_requires_auth(raw_client):
    response = raw_client.post(
        "/api/alignment/run",
        json={
            "project_id": "WetlabDB",
            "series_id": "Compounds",
            "compound_ids": ["x"],
            "reference_id": "x",
        },
    )
    assert response.status_code == 401


def test_alignment_project_approve_and_lock(employee_client):
    listed = employee_client.get(
        "/api/databases/WetlabDB/collections/Compounds/compounds"
    ).json()["compounds"]
    aspirin = next(c for c in listed if c["Name"] == "Aspirin")
    cid = aspirin["_id"]

    run = employee_client.post(
        "/api/alignment/run",
        json={
            "project_id": "WetlabDB",
            "series_id": "Compounds",
            "database": "WetlabDB",
            "collection": "Compounds",
            "compound_ids": [cid],
            "assay_ids": [],
            "reference_id": cid,
            "core_smarts": "c1ccccc1",
        },
    ).json()

    created = employee_client.post(
        "/api/alignment-projects",
        json={
            "project_id": "WetlabDB",
            "series_id": "Compounds",
            "database": "WetlabDB",
            "collection": "Compounds",
            "compound_ids": [cid],
            "assay_ids": [],
            "reference_id": cid,
            "mode": "same_scaffold",
            "core_smarts": "c1ccccc1",
            "snapshot_revision": run["snapshot_revision"],
            "draft_solution": run,
        },
    )
    assert created.status_code == 200
    body = created.json()
    pid = body["id"]

    approved = employee_client.post(
        f"/api/alignment-projects/{pid}/approve",
        json={
            "expected_version": body["version"],
            "snapshot_revision": run["snapshot_revision"],
            "database": "WetlabDB",
            "collection": "Compounds",
        },
    )
    assert approved.status_code == 200

    listed = employee_client.get(
        "/api/alignment-projects",
        params={"project_id": "WetlabDB", "series_id": "Compounds"},
    )
    assert listed.status_code == 200
    ids = [p["id"] for p in listed.json()["projects"]]
    assert pid in ids
    assert listed.json()["projects"][0]["compound_count"] >= 1

    blocked = employee_client.patch(
        f"/api/alignment-projects/{pid}",
        json={
            "expected_version": approved.json()["version"],
            "draft_solution": {**run, "user_message": "mutated"},
            "database": "WetlabDB",
            "collection": "Compounds",
        },
    )
    assert blocked.status_code == 409


def test_sar_limits(user_client):
    body = user_client.get("/api/sar/limits").json()
    assert body["max_alignment_compounds"] >= 200
    assert body["live_align_max_compounds"] == 15
    assert "S01" in body["status_case_messages"]


def test_alignment_run_same_scaffold(employee_client):
    listed = employee_client.get(
        "/api/databases/WetlabDB/collections/Compounds/compounds"
    ).json()["compounds"]
    aspirin = next(c for c in listed if c["Name"] == "Aspirin")
    cid = aspirin["_id"]

    response = employee_client.post(
        "/api/alignment/run",
        json={
            "project_id": "WetlabDB",
            "series_id": "Compounds",
            "database": "WetlabDB",
            "collection": "Compounds",
            "compound_ids": [cid],
            "assay_ids": [],
            "reference_id": cid,
            "core_smarts": "c1ccccc1",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "OPTIMAL"
    assert len(body["layouts"]) == 1
    assert body["layouts"][0]["molecule_id"] == cid
    assert body["layouts"][0]["molblock"]
    assert "V2000" in body["layouts"][0]["molblock"]
    assert body["snapshot_revision"]


def test_core_preview_and_depict(user_client):
    preview = user_client.post(
        "/api/sar/core-preview",
        json={
            "reference_smiles": "c1ccccc1",
            "core_atoms": [0, 1, 2, 3, 4, 5],
            "molecules": [
                {"id": "phcl", "smiles": "Clc1ccccc1"},
                {"id": "pyr", "smiles": "n1ccccc1"},
            ],
            "atom_modes": {"0": "group"},
        },
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["connected"] is True
    assert body["smarts"]
    by_id = {m["id"]: m for m in body["matches"]}
    assert by_id["phcl"]["matched"] is True
    assert by_id["pyr"]["matched"] is True

    drawn = user_client.post(
        "/api/sar/depict",
        json={"smiles": "c1ccccc1", "width": 200, "height": 160, "selected": [0, 1]},
    )
    assert drawn.status_code == 200, drawn.text
    svg = drawn.json()
    assert "<svg" in svg["svg"]
    assert len(svg["atoms"]) == 6
    assert svg["atoms"][0]["neighbors"]
