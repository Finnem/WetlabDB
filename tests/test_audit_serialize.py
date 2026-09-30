"""Audit JSON serialization for API responses."""

from __future__ import annotations

from wetlabdb.api.audit_serialize import serialize_audit_events


def test_strips_objectid_like_id():
    rows = [{"_id": "507f1f77bcf86cd799439011", "at": "2026-01-01T00:00:00Z", "action": "login.success", "target": "user:admin", "summary": {}, "actor": "admin"}]
    out = serialize_audit_events(rows)
    assert "_id" not in out[0]
    assert out[0]["action"] == "login.success"
