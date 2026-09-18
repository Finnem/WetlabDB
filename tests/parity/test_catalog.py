"""Parity: database / collection catalog."""

from __future__ import annotations

from wetlabdb.services.catalog import HIDDEN_DATABASE_NAMES


def test_list_databases_hides_system_names(admin_client):
    names = admin_client.get("/api/databases").json()["databases"]
    assert "WetlabDB" in names
    for hidden in HIDDEN_DATABASE_NAMES:
        assert hidden not in names
    assert all(not n.startswith(".") for n in names)


def test_list_collections(admin_client):
    names = admin_client.get("/api/databases/WetlabDB/collections").json()[
        "collections"
    ]
    assert "Compounds" in names


def test_admin_create_and_drop_database(admin_client):
    created = admin_client.post(
        "/api/databases", json={"name": "ScratchDB", "collection": "Things"}
    )
    assert created.status_code == 201
    names = admin_client.get("/api/databases").json()["databases"]
    assert "ScratchDB" in names
    colls = admin_client.get("/api/databases/ScratchDB/collections").json()[
        "collections"
    ]
    assert "Things" in colls
    dropped = admin_client.delete("/api/databases/ScratchDB")
    assert dropped.status_code == 200
    names = admin_client.get("/api/databases").json()["databases"]
    assert "ScratchDB" not in names


def test_drop_nonexistent_database_is_idempotent(admin_client):
    response = admin_client.delete("/api/databases/DoesNotExist")
    assert response.status_code == 200


def test_cannot_use_reserved_database_name(admin_client):
    response = admin_client.post(
        "/api/databases",
        json={"name": "wetlabdb_meta", "collection": "users"},
    )
    assert response.status_code == 400


def test_hidden_database_is_not_addressable(admin_client):
    response = admin_client.get("/api/databases/wetlabdb_meta/collections")
    assert response.status_code == 404


def test_admin_create_and_drop_collection(admin_client):
    created = admin_client.post(
        "/api/databases/WetlabDB/collections", json={"name": "Scratch"}
    )
    assert created.status_code == 201
    names = admin_client.get("/api/databases/WetlabDB/collections").json()[
        "collections"
    ]
    assert "Scratch" in names
    dropped = admin_client.delete("/api/databases/WetlabDB/collections/Scratch")
    assert dropped.status_code == 200
    names = admin_client.get("/api/databases/WetlabDB/collections").json()[
        "collections"
    ]
    assert "Scratch" not in names
