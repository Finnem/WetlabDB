"""Parity: soft delete, restore, revisions, CSV preview, audit read."""

from __future__ import annotations


def test_soft_delete_hides_from_list(admin_client):
    created = admin_client.post(
        "/api/databases/WetlabDB/collections/Compounds/compounds",
        json={"data": {"Name": "TrashMe", "SMILES": "CC"}},
    )
    doc_id = created.json()["_id"]
    deleted = admin_client.delete(
        f"/api/databases/WetlabDB/collections/Compounds/compounds/{doc_id}"
    )
    assert deleted.status_code == 200
    assert deleted.json()["permanent"] is False

    missing = admin_client.get(
        f"/api/databases/WetlabDB/collections/Compounds/compounds/{doc_id}"
    )
    assert missing.status_code == 404

    listed = admin_client.get(
        "/api/databases/WetlabDB/collections/Compounds/compounds"
    ).json()["compounds"]
    assert doc_id not in {c["_id"] for c in listed}

    trash = admin_client.get(
        "/api/databases/WetlabDB/collections/Compounds/compounds/deleted"
    )
    assert trash.status_code == 200
    ids = {c["_id"] for c in trash.json()["compounds"]}
    assert doc_id in ids


def test_restore_after_soft_delete(admin_client):
    created = admin_client.post(
        "/api/databases/WetlabDB/collections/Compounds/compounds",
        json={"data": {"Name": "RestoreMe", "SMILES": "CCO"}},
    )
    doc_id = created.json()["_id"]
    admin_client.delete(f"/api/databases/WetlabDB/collections/Compounds/compounds/{doc_id}")
    restored = admin_client.post(
        f"/api/databases/WetlabDB/collections/Compounds/compounds/{doc_id}/restore"
    )
    assert restored.status_code == 200
    assert restored.json()["Name"] == "RestoreMe"


def test_hard_delete_requires_admin(employee_client, admin_client):
    created = admin_client.post(
        "/api/databases/WetlabDB/collections/Compounds/compounds",
        json={"data": {"Name": "HardDel", "SMILES": "C"}},
    )
    doc_id = created.json()["_id"]
    denied = employee_client.delete(
        f"/api/databases/WetlabDB/collections/Compounds/compounds/{doc_id}",
        params={"hard": "true"},
    )
    assert denied.status_code == 403
    ok = admin_client.delete(
        f"/api/databases/WetlabDB/collections/Compounds/compounds/{doc_id}",
        params={"hard": "true"},
    )
    assert ok.status_code == 200
    assert ok.json()["permanent"] is True


def test_update_records_revision(admin_client):
    created = admin_client.post(
        "/api/databases/WetlabDB/collections/Compounds/compounds",
        json={"data": {"Name": "Rev", "SMILES": "CC"}},
    )
    doc_id = created.json()["_id"]
    admin_client.put(
        f"/api/databases/WetlabDB/collections/Compounds/compounds/{doc_id}",
        json={"data": {"Name": "Rev2"}},
    )
    revs = admin_client.get(
        f"/api/databases/WetlabDB/collections/Compounds/compounds/{doc_id}/revisions"
    )
    assert revs.status_code == 200
    body = revs.json()["revisions"]
    assert len(body) == 1
    assert body[0]["document"]["Name"] == "Rev"


def test_csv_preview_dry_run(admin_client):
    csv_text = "Name,SMILES\nPreviewRow,CC\n"
    preview = admin_client.post(
        "/api/databases/WetlabDB/collections/Compounds/csv/preview",
        files={"file": ("in.csv", csv_text, "text/csv")},
        data={"identifier_col": "Name", "data_cols": "SMILES"},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["dry_run"] is True
    assert body["created"] == 1

    listed = admin_client.get(
        "/api/databases/WetlabDB/collections/Compounds/compounds"
    ).json()["compounds"]
    assert "PreviewRow" not in {c["Name"] for c in listed}


def test_audit_events_admin_only(user_client, admin_client):
    assert user_client.get("/api/audit/events").status_code == 403
    events = admin_client.get("/api/audit/events", params={"limit": 5})
    assert events.status_code == 200
    assert "events" in events.json()
