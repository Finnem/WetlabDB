"""Contract test: identical assertions across both backends.

Parametrising over ``LocalClient`` and ``MongoClientAdapter`` (wrapping a
``mongomock.MongoClient``) catches API drift between the two implementations
without requiring a live MongoDB server.
"""

from __future__ import annotations

import pytest

from wetlabdb.storage import (
    CollectionProto,
    DatabaseProto,
    StorageClientProto,
    coerce_id,
    get_local_client,
)
from wetlabdb.storage.mongo import MongoClientAdapter


@pytest.fixture(params=["local", "mongomock"])
def client(request, tmp_path):
    if request.param == "local":
        return get_local_client(str(tmp_path), bootstrap_db=None)

    mongomock = pytest.importorskip("mongomock")
    return MongoClientAdapter(mongomock.MongoClient())


def test_implements_protocol(client):
    assert isinstance(client, StorageClientProto)
    db = client["TestDB"]
    assert isinstance(db, DatabaseProto)
    coll = db.create_collection("Things")
    assert isinstance(coll, CollectionProto)


def test_full_crud_cycle(client):
    db = client["TestDB"]
    coll = db.create_collection("Things")

    rid = coll.insert_one({"name": "alpha", "n": 1}).inserted_id
    assert coll.count_documents() == 1

    fetched = coll.find_one({"_id": coerce_id(rid)})
    assert fetched is not None and fetched["name"] == "alpha"

    upd = coll.update_one({"_id": coerce_id(rid)}, {"$set": {"n": 42}})
    assert upd.matched_count == 1 and upd.modified_count == 1
    assert coll.find_one({"_id": coerce_id(rid)})["n"] == 42

    deld = coll.delete_one({"_id": coerce_id(rid)})
    assert deld.deleted_count == 1
    assert coll.count_documents() == 0


def test_find_filters(client):
    db = client["TestDB"]
    coll = db.create_collection("Items")
    for v in ["a", "b", "a"]:
        coll.insert_one({"k": v})
    assert len(coll.find({"k": "a"})) == 2
    assert len(coll.find({"k": "b"})) == 1
    assert len(coll.find()) == 3


def test_no_match_returns_zero_counts(client):
    coll = client["TestDB"].create_collection("Empty")
    coll.insert_one({"a": 1})
    assert coll.delete_one({"a": 999}).deleted_count == 0
    upd = coll.update_one({"a": 999}, {"$set": {"a": 2}})
    assert upd.matched_count == 0 and upd.modified_count == 0
    assert coll.find_one({"a": 999}) is None


def test_drop_database_removes_db_from_listing(client):
    """Both backends must let admin code drop a database by name.

    Required by the GUI's "Delete database" admin action; without this
    the protocol-typed call site would crash on one backend or the other.
    """
    db = client["TempDB"]
    db.create_collection("Things").insert_one({"x": 1})
    assert "TempDB" in client.list_database_names()

    client.drop_database("TempDB")
    assert "TempDB" not in client.list_database_names()


def test_drop_nonexistent_database_is_noop(client):
    """Idempotency: dropping a DB that isn't there must not raise."""
    client.drop_database("DoesNotExist")
    assert "DoesNotExist" not in client.list_database_names()
