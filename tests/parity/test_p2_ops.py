"""Parity: pagination and health probes."""

from __future__ import annotations


def test_compound_list_pagination(admin_client):
    for index in range(3):
        admin_client.post(
            "/api/databases/WetlabDB/collections/Compounds/compounds",
            json={"data": {"Name": f"Page{index}", "SMILES": "C"}},
        )
    first = admin_client.get(
        "/api/databases/WetlabDB/collections/Compounds/compounds",
        params={"limit": 2},
    )
    assert first.status_code == 200
    body = first.json()
    assert len(body["compounds"]) == 2
    assert body["limit"] == 2
    assert body.get("next_cursor")

    second = admin_client.get(
        "/api/databases/WetlabDB/collections/Compounds/compounds",
        params={"limit": 2, "cursor": body["next_cursor"]},
    )
    assert second.status_code == 200
    ids1 = {c["_id"] for c in body["compounds"]}
    ids2 = {c["_id"] for c in second.json()["compounds"]}
    assert ids1.isdisjoint(ids2)


def test_readiness_public(raw_client):
    live = raw_client.get("/api/health/live")
    assert live.status_code == 200
    ready = raw_client.get("/api/health/ready")
    assert ready.status_code == 200
    assert ready.json()["ok"] is True


def test_operation_limits(admin_client, raw_client):
    assert raw_client.get("/api/limits").status_code == 401
    body = admin_client.get("/api/limits").json()
    assert body["csv_max_rows"] == 10_000
    assert body["compound_page_max"] == 500


def test_metrics_admin_only(user_client, admin_client):
    assert user_client.get("/api/metrics").status_code == 403
    metrics = admin_client.get("/api/metrics")
    assert metrics.status_code == 200
    assert "http_requests" in metrics.json()
    prom = admin_client.get("/api/metrics/prometheus")
    assert prom.status_code == 200
    assert "wetlabdb_http_requests_total" in prom.text
