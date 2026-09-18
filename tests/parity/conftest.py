"""Shared fixtures for the HTTP parity suite."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from wetlabdb.api.app import create_app
from wetlabdb.services.auth import AuthService
from wetlabdb.services.compounds import CompoundService
from wetlabdb.settings import Settings
from wetlabdb.storage.local import get_local_client
from wetlabdb.storage.mongo import MongoClientAdapter


@pytest.fixture(params=["local", "mongomock"])
def backend(request, tmp_path, sample_compounds):
    """Storage + auth wired the same way production is, minus the network."""
    if request.param == "local":
        client = get_local_client(str(tmp_path), bootstrap_db=None)
        auth = AuthService.json_store(str(tmp_path))
        mode = "local"
    else:
        mongomock = pytest.importorskip("mongomock")
        client = MongoClientAdapter(mongomock.MongoClient())
        auth = AuthService.mongo_store(client)
        mode = "remote"

    settings = Settings(
        mode=mode,
        data_dir=str(tmp_path),
        session_secret="test-secret-not-for-production",
        admin_user="admin",
        admin_password="adminpass",
    )
    auth.bootstrap(settings.admin_user, settings.admin_password)
    auth.create_user("user", "userpass", admin=False)

    db = client["WetlabDB"]
    coll = db.create_collection("Compounds")
    svc = CompoundService(coll)
    for doc in sample_compounds:
        svc.add(doc)
    svc.add({"Name": "Extra", "SMILES": "CCO", "LabNote": "dynamic-field"})

    app = create_app(
        settings=settings, client=client, auth=auth, mount_spa=False
    )
    return {
        "app": app,
        "client": client,
        "auth": auth,
        "settings": settings,
        "mode": request.param,
    }


@pytest.fixture
def app(backend):
    return backend["app"]


@pytest.fixture
def raw_client(app):
    """Unauthenticated TestClient."""
    return TestClient(app)


@pytest.fixture
def admin_client(app):
    client = TestClient(app)
    response = client.post(
        "/api/login", json={"username": "admin", "password": "adminpass"}
    )
    assert response.status_code == 200, response.text
    return client


@pytest.fixture
def user_client(app):
    client = TestClient(app)
    response = client.post(
        "/api/login", json={"username": "user", "password": "userpass"}
    )
    assert response.status_code == 200, response.text
    return client
