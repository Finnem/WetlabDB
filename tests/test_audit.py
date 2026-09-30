"""Audit log service tests."""

from __future__ import annotations

import json

from wetlabdb.services.audit import AuditService, JsonlAuditStore


def test_jsonl_audit_store_appends(tmp_path):
    store = JsonlAuditStore(str(tmp_path))
    svc = AuditService(store)
    svc.record(action="login.success", target="user:admin", actor="admin", request_id="req-1")
    svc.record(action="compound.create", target="WetlabDB/Compounds/x", actor="admin")
    path = tmp_path / ".wetlabdb" / "audit.jsonl"
    assert path.is_file()
    row = json.loads(path.read_text(encoding="utf-8").strip().splitlines()[0])
    assert row["action"] == "login.success"
    assert row["actor"] == "admin"
    assert row["request_id"] == "req-1"
    recent = svc.list_recent(limit=10)
    assert recent[0]["action"] == "compound.create"
