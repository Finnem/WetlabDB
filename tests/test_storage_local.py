"""Tests for the JSON-file backed local storage backend."""

from __future__ import annotations

import json
import os

import pytest

from wetlabdb.storage import (
    LocalClient,
    LocalCollection,
    coerce_id,
    get_local_client,
)


def test_bootstrap_creates_default_db_and_collection(tmp_path):
    client = get_local_client(str(tmp_path))
    assert client.list_database_names() == ["WetlabDB"]
    assert client["WetlabDB"].list_collection_names() == ["Compounds"]


def test_bootstrap_disabled(tmp_path):
    client = get_local_client(str(tmp_path), bootstrap_db=None)
    assert client.list_database_names() == []


def test_crud_round_trip_and_persistence(tmp_path, sample_compounds):
    client = get_local_client(str(tmp_path))
    coll = client["WetlabDB"]["Compounds"]

    inserted_ids = [coll.insert_one(doc).inserted_id for doc in sample_compounds]
    assert all(len(i) == 24 for i in inserted_ids)
    assert coll.count_documents() == 3

    fetched = coll.find_one({"_id": coerce_id(inserted_ids[0])})
    assert fetched is not None
    assert fetched["Name"] == "Aspirin"

    upd = coll.update_one(
        {"_id": coerce_id(inserted_ids[1])},
        {"$set": {"Pure": True, "Notes": "fresh"}},
    )
    assert (upd.matched_count, upd.modified_count) == (1, 1)

    # Reopen the client to verify persistence across "sessions".
    client2 = LocalClient(str(tmp_path))
    coll2 = client2["WetlabDB"]["Compounds"]
    caffeine = coll2.find_one({"_id": coerce_id(inserted_ids[1])})
    assert caffeine["Pure"] is True
    assert caffeine["Notes"] == "fresh"

    # ``$unset`` removes the field.
    coll2.update_one(
        {"_id": coerce_id(inserted_ids[1])},
        {"$unset": ["Notes"]},
    )
    assert "Notes" not in coll2.find_one({"_id": coerce_id(inserted_ids[1])})


def test_atomic_write_does_not_leave_tmp_file(tmp_path):
    coll = LocalCollection(str(tmp_path / "x.json"))
    coll.insert_one({"a": 1})
    files = sorted(os.listdir(tmp_path))
    assert files == ["x.json"], f"unexpected leftover files: {files}"


def test_delete_one_no_match(tmp_path):
    coll = LocalCollection(str(tmp_path / "x.json"))
    coll.insert_one({"a": 1})
    assert coll.delete_one({"a": 999}).deleted_count == 0


def test_update_one_no_match(tmp_path):
    coll = LocalCollection(str(tmp_path / "x.json"))
    coll.insert_one({"a": 1})
    upd = coll.update_one({"a": 999}, {"$set": {"a": 2}})
    assert upd.matched_count == 0
    assert upd.modified_count == 0


def test_find_with_and_without_filter(tmp_path, sample_compounds):
    coll = LocalCollection(str(tmp_path / "compounds.json"))
    for doc in sample_compounds:
        coll.insert_one(doc)
    assert len(coll.find()) == 3
    assert [d["Name"] for d in coll.find({"Name": "Caffeine"})] == ["Caffeine"]


def test_find_one_returns_first_match(tmp_path):
    coll = LocalCollection(str(tmp_path / "x.json"))
    coll.insert_one({"k": "v", "n": 1})
    coll.insert_one({"k": "v", "n": 2})
    assert coll.find_one({"k": "v"})["n"] == 1


def test_corrupted_file_returns_empty_list(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not valid json", encoding="utf-8")
    coll = LocalCollection(str(path))
    assert coll.find() == []


def test_create_collection_rejects_duplicates(tmp_path):
    db = get_local_client(str(tmp_path))["WetlabDB"]
    with pytest.raises(ValueError):
        db.create_collection("Compounds")


def test_drop_collection_and_drop_database(tmp_path):
    client = get_local_client(str(tmp_path))
    db = client["WetlabDB"]
    db.create_collection("Reactions")
    assert sorted(db.list_collection_names()) == ["Compounds", "Reactions"]
    db.drop_collection("Reactions")
    assert db.list_collection_names() == ["Compounds"]

    client.drop_database("WetlabDB")
    assert client.list_database_names() == []


def test_id_filter_matches_string_or_objectid_form(tmp_path):
    coll = LocalCollection(str(tmp_path / "x.json"))
    rid = coll.insert_one({"v": 1}).inserted_id
    by_str = coll.find_one({"_id": rid})
    by_coerced = coll.find_one({"_id": coerce_id(rid)})
    assert by_str == by_coerced
    assert by_str is not None


def test_persisted_json_is_human_readable(tmp_path):
    coll = LocalCollection(str(tmp_path / "x.json"))
    coll.insert_one({"Name": "Aspirin"})
    raw = json.loads((tmp_path / "x.json").read_text(encoding="utf-8"))
    assert raw[0]["Name"] == "Aspirin"
