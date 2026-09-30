"""API mutation header and login rate limiting."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from wetlabdb.api.app import create_app
from wetlabdb.api.rate_limit import LoginRateLimiter
from wetlabdb.services.auth import AuthService
from wetlabdb.settings import Settings
from wetlabdb.storage.local import get_local_client

MUTATION_HEADER = {"X-WetlabDB-Request": "1"}


@pytest.fixture
def secured_app(tmp_path):
    client = get_local_client(str(tmp_path), bootstrap_db=None)
    auth = AuthService.json_store(str(tmp_path))
    settings = Settings(
        mode="local",
        data_dir=str(tmp_path),
        session_secret="x" * 40,
        admin_user="admin",
        admin_password="adminpass",
    )
    auth.bootstrap(settings.admin_user, settings.admin_password)
    app = create_app(settings=settings, client=client, auth=auth, mount_spa=False)
    app.state.login_rate_limiter = LoginRateLimiter(max_failures=3, window_seconds=60)
    return app


def test_mutating_api_without_header_is_forbidden(secured_app):
    client = TestClient(secured_app)
    response = client.post("/api/logout")
    assert response.status_code == 403


def test_mutating_api_with_header_allowed(secured_app):
    client = TestClient(secured_app, headers=MUTATION_HEADER)
    client.post("/api/login", json={"username": "admin", "password": "adminpass"})
    response = client.post("/api/logout", headers=MUTATION_HEADER)
    assert response.status_code == 200


def test_login_rate_limit(secured_app):
    client = TestClient(secured_app)
    for _ in range(3):
        bad = client.post("/api/login", json={"username": "admin", "password": "wrong"})
        assert bad.status_code == 401
    blocked = client.post("/api/login", json={"username": "admin", "password": "wrong"})
    assert blocked.status_code == 429
