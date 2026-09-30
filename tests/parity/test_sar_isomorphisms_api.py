"""API parity: scaffold mapping modes on alignment run."""

from __future__ import annotations

import json


def _add(admin_client, name: str, smiles: str) -> str:
    r = admin_client.post(
        "/api/databases/WetlabDB/collections/Compounds/compounds",
        json={"data": {"Name": name, "SMILES": smiles}},
    )
    assert r.status_code == 201, r.text
    return r.json()["_id"]


def test_alignment_api_from_smarts(admin_client):
    ref_id = _add(admin_client, "IsoRef", "c1sccn1")
    analog_id = _add(admin_client, "IsoThia", "Cc1sccn1")
    resp = admin_client.post(
        "/api/alignment/run",
        json={
            "project_id": "WetlabDB",
            "series_id": "Compounds",
            "compound_ids": [ref_id, analog_id],
            "assay_ids": [],
            "reference_id": ref_id,
            "mode": "same_scaffold",
            "core_smarts": "c1sccn1",
            "scaffold_element_mode": "from_smarts",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "OPTIMAL"
    assert body["details"].get("scaffold_element_mode") == "from_smarts"
    assert len(body["layouts"]) == 2


def test_alignment_api_element_agnostic_matches_oxazole(admin_client):
    ref_id = _add(admin_client, "IsoRef2", "c1sccn1")
    ox_id = _add(admin_client, "IsoOx", "c1occn1")
    resp = admin_client.post(
        "/api/alignment/run",
        json={
            "project_id": "WetlabDB",
            "series_id": "Compounds",
            "compound_ids": [ref_id, ox_id],
            "assay_ids": [],
            "reference_id": ref_id,
            "mode": "same_scaffold",
            "core_smarts": "c1sccn1",
            "scaffold_element_mode": "element_agnostic",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "OPTIMAL"
    assert body["details"].get("scaffold_element_mode") == "element_agnostic"
    assert len(body["layouts"]) == 2


def test_alignment_progress_stream(admin_client):
    ref_id = _add(admin_client, "ProgRef", "c1ccccc1")
    analog_id = _add(admin_client, "ProgCl", "Clc1ccccc1")
    resp = admin_client.post(
        "/api/alignment/run-progress",
        json={
            "project_id": "WetlabDB",
            "series_id": "Compounds",
            "compound_ids": [ref_id, analog_id],
            "assay_ids": [],
            "reference_id": ref_id,
            "mode": "same_scaffold",
            "core_smarts": "c1ccccc1",
        },
    )
    assert resp.status_code == 200, resp.text
    assert "ndjson" in resp.headers.get("content-type", "")
    events = [json.loads(line) for line in resp.text.splitlines() if line.strip()]
    phases = [row["phase"] for row in events]
    assert "ingest" in phases
    assert "mapping" in phases
    assert "optimize" in phases
    assert "layout" in phases
    assert events[-1]["phase"] == "done"
    assert events[-1]["result"]["status"] == "OPTIMAL"
    assert len(events[-1]["result"]["layouts"]) == 2
