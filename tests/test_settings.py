"""Tests for :class:`wetlabdb.settings.Settings`."""

from __future__ import annotations

from wetlabdb.settings import Settings


def test_from_env_reads_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("WETLABDB_MODE", "remote")
    monkeypatch.setenv("MONGO_URI", "mongodb://example:27017")
    monkeypatch.setenv("WETLABDB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WETLABDB_SESSION_SECRET", "secret")
    monkeypatch.setenv("WETLABDB_ADMIN_USER", "root")
    monkeypatch.setenv("WETLABDB_ADMIN_PASSWORD", "pw")
    settings = Settings.from_env()
    assert settings.mode == "remote"
    assert settings.mongo_uri == "mongodb://example:27017"
    assert settings.admin_user == "root"
    assert settings.admin_password == "pw"
    assert not settings.is_local
