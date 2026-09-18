"""Parity: login, sessions, admin vs non-admin."""

from __future__ import annotations

from wetlabdb.services.auth import AuthService, META_DATABASE


def test_unauthenticated_compounds_return_401(raw_client):
    response = raw_client.get("/api/databases/WetlabDB/collections/Compounds/compounds")
    assert response.status_code == 401


def test_unauthenticated_search_returns_401(raw_client):
    response = raw_client.post(
        "/api/databases/WetlabDB/collections/Compounds/search/similarity",
        json={"query": "CCO"},
    )
    assert response.status_code == 401


def test_unauthenticated_csv_export_returns_401(raw_client):
    response = raw_client.get(
        "/api/databases/WetlabDB/collections/Compounds/csv/export"
    )
    assert response.status_code == 401


def test_wrong_password_fails(raw_client):
    response = raw_client.post(
        "/api/login", json={"username": "admin", "password": "nope"}
    )
    assert response.status_code == 401


def test_login_sets_session_and_me(admin_client):
    me = admin_client.get("/api/me")
    assert me.status_code == 200
    body = me.json()
    assert body["username"] == "admin"
    assert body["admin"] is True
    assert "password" not in body
    assert "password_hash" not in body


def test_non_admin_me_flag(user_client):
    body = user_client.get("/api/me").json()
    assert body["username"] == "user"
    assert body["admin"] is False


def test_non_admin_cannot_create_database(user_client):
    response = user_client.post(
        "/api/databases", json={"name": "Scratch", "collection": "X"}
    )
    assert response.status_code == 403


def test_non_admin_cannot_drop_collection(user_client):
    response = user_client.delete("/api/databases/WetlabDB/collections/Compounds")
    assert response.status_code == 403


def test_non_admin_cannot_list_users(user_client):
    response = user_client.get("/api/users")
    assert response.status_code == 403


def test_non_admin_can_crud_compounds(user_client):
    created = user_client.post(
        "/api/databases/WetlabDB/collections/Compounds/compounds",
        json={"data": {"Name": "UserAdd", "SMILES": "CC"}},
    )
    assert created.status_code == 201
    doc_id = created.json()["_id"]
    fetched = user_client.get(
        f"/api/databases/WetlabDB/collections/Compounds/compounds/{doc_id}"
    )
    assert fetched.status_code == 200
    assert fetched.json()["Name"] == "UserAdd"


def test_login_does_not_accept_mongo_credentials_shape(raw_client):
    """New rule: the browser never sends Mongo host/user/password."""
    response = raw_client.post(
        "/api/login",
        json={
            "username": "admin",
            "password": "adminpass",
            "host": "mongodb://evil",
            "auth_source": "admin",
        },
    )
    # Extra fields are ignored by pydantic; login still uses app accounts.
    assert response.status_code == 200
    assert response.json()["username"] == "admin"


def test_bootstrap_does_not_overwrite_existing_admin(backend, tmp_path):
    auth: AuthService = backend["auth"]
    first = auth.get("admin")
    assert first is not None
    original_hash = first.password_hash
    again = auth.bootstrap("admin", "a-different-password")
    assert again is None
    assert auth.get("admin").password_hash == original_hash


def test_local_users_file_path(backend, tmp_path):
    if backend["mode"] != "local":
        return
    users_file = tmp_path / ".wetlabdb" / "users.json"
    assert users_file.is_file()


def test_mongo_users_live_in_meta_db(backend):
    if backend["mode"] != "mongomock":
        return
    names = backend["client"].list_database_names()
    assert META_DATABASE in names


def test_health_is_public(raw_client):
    assert raw_client.get("/api/health").status_code == 200
