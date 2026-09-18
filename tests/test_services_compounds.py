"""Tests for :class:`wetlabdb.services.CompoundService`."""

from __future__ import annotations

import pytest

from wetlabdb.services import CompoundService
from wetlabdb.storage import LocalCollection, ObjectId, coerce_id


@pytest.fixture
def service(tmp_path):
    coll = LocalCollection(str(tmp_path / "x.json"))
    return CompoundService(coll)


def test_add_and_get_round_trip(service):
    rid = service.add({"Name": "Aspirin", "SMILES": "CC(=O)Oc1ccccc1C(=O)O"})
    assert isinstance(rid, str) and len(rid) == 24

    fetched = service.get(rid)
    assert fetched is not None
    assert fetched["Name"] == "Aspirin"


def test_get_with_objectid_input(service):
    rid = service.add({"Name": "x"})
    via_str = service.get(rid)
    via_obj = service.get(ObjectId(rid))
    assert via_str == via_obj


def test_update(service):
    rid = service.add({"Name": "Caffeine"})
    assert service.update(rid, {"Pure": True}) is True
    assert service.get(rid)["Pure"] is True


def test_update_with_unset(service):
    rid = service.add({"Name": "Caffeine", "Note": "scratch"})
    assert service.update(rid, {}, unset=["Note"]) is True
    assert "Note" not in service.get(rid)


def test_update_missing_returns_false(service):
    assert service.update("000000000000000000000000", {"Pure": True}) is False


def test_update_with_no_changes_returns_false(service):
    rid = service.add({"Name": "x"})
    assert service.update(rid, {}) is False


def test_delete(service):
    rid = service.add({"Name": "x"})
    assert service.delete(rid) is True
    assert service.get(rid) is None
    assert service.delete(rid) is False  # second time -> nothing to delete


def test_count_and_list_all(service, sample_compounds):
    for doc in sample_compounds:
        service.add(doc)
    assert service.count() == 3
    assert {d["Name"] for d in service.list_all()} == {
        d["Name"] for d in sample_compounds
    }


def test_count_with_filter(service):
    service.add({"Name": "a", "Pure": True})
    service.add({"Name": "b", "Pure": False})
    service.add({"Name": "c", "Pure": True})
    assert service.count({"Pure": True}) == 2


def test_get_with_invalid_id_returns_none(service):
    # Coerced to a string that simply doesn't match any document.
    assert service.get("nonexistent-id") is None


def test_get_none_returns_none(service):
    assert service.get(None) is None
    assert coerce_id(None) is None


def test_list_filtered_all_and_column(service):
    service.add({"Name": "Aspirin", "CAS Nr": "50-78-2"})
    service.add({"Name": "Caffeine", "CAS Nr": "58-08-2"})
    hits = service.list_filtered("aspirin", column="All")
    assert [d["Name"] for d in hits] == ["Aspirin"]
    hits = service.list_filtered("58-08-2", column="CAS Nr")
    assert [d["Name"] for d in hits] == ["Caffeine"]
    hits = service.list_filtered("58-08-2", column="Name")
    assert hits == []
    assert len(service.list_filtered("")) == 2
