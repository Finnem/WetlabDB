"""Tests for :class:`wetlabdb.settings.Settings`."""

from __future__ import annotations

import pytest

from wetlabdb.api.app import create_app
from wetlabdb.settings import Settings


def test_from_env_reads_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("WETLABDB_MODE", "remote")
    monkeypatch.setenv("MONGO_URI", "mongodb://example:27017")
    monkeypatch.setenv("WETLABDB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WETLABDB_SESSION_SECRET", "x" * 40)
    monkeypatch.setenv("WETLABDB_ADMIN_USER", "root")
    monkeypatch.setenv("WETLABDB_ADMIN_PASSWORD", "pw")
    settings = Settings.from_env()
    assert settings.mode == "remote"
    assert settings.mongo_uri == "mongodb://example:27017"
    assert settings.admin_user == "root"
    assert settings.admin_password == "pw"
    assert not settings.is_local


def test_remote_rejects_weak_session_secret():
    settings = Settings(
        mode="remote",
        session_secret="change-me",
        admin_password="strong-password-here",
    )
    with pytest.raises(ValueError, match="WETLABDB_SESSION_SECRET"):
        settings.validate_for_runtime()


def test_remote_rejects_default_admin_password():
    settings = Settings(
        mode="remote",
        session_secret="x" * 40,
        admin_password="admin",
    )
    with pytest.raises(ValueError, match="WETLABDB_ADMIN_PASSWORD"):
        settings.validate_for_runtime()


def test_create_app_remote_validates_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("WETLABDB_ALLOW_INSECURE_DEV", "")
    settings = Settings(
        mode="remote",
        data_dir=str(tmp_path),
        session_secret="change-me",
        admin_password="admin",
    )
    with pytest.raises(ValueError):
        create_app(settings=settings, mount_spa=False)
