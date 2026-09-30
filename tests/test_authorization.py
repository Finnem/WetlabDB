"""Unit tests for collection authorization."""

from __future__ import annotations

import pytest

from wetlabdb.services.auth import User
from wetlabdb.services.authorization import AuthorizationService, CollectionAccessPolicy, JsonPolicyStore
from wetlabdb.services.catalog import CatalogService


class _FakeClient:
    def __init__(self, dbs: dict[str, list[str]]) -> None:
        self._dbs = dbs

    def list_database_names(self):
        return list(self._dbs.keys())

    def __getitem__(self, name: str):
        return _FakeDb(self._dbs.get(name, []))


class _FakeDb:
    def __init__(self, colls: list[str]) -> None:
        self._colls = colls

    def list_collection_names(self):
        return list(self._colls)


def test_student_viewer_employee_editor_default(tmp_path):
    store = JsonPolicyStore(str(tmp_path))
    catalog = CatalogService(_FakeClient({"WetlabDB": ["Compounds"]}))
    authz = AuthorizationService(store, catalog)
    authz.ensure_default_policy("WetlabDB", "Compounds")

    student = User(username="s1", password_hash="x", admin=False, kind="student")
    employee = User(username="e1", password_hash="x", admin=False, kind="employee")

    assert authz.can_view(student, "WetlabDB", "Compounds")
    assert not authz.can_edit(student, "WetlabDB", "Compounds")
    assert authz.can_edit(employee, "WetlabDB", "Compounds")


def test_owner_only_blocks_others(tmp_path):
    store = JsonPolicyStore(str(tmp_path))
    catalog = CatalogService(_FakeClient({"WetlabDB": ["Private"]}))
    authz = AuthorizationService(store, catalog)
    authz._store.upsert(
        CollectionAccessPolicy(
            database="WetlabDB",
            collection="Private",
            owner="owner1",
            visibility="owner_only",
        )
    )
    owner = User(username="owner1", password_hash="x", admin=False, kind="employee")
    other = User(username="other", password_hash="x", admin=False, kind="employee")

    assert authz.can_edit(owner, "WetlabDB", "Private")
    assert not authz.can_view(other, "WetlabDB", "Private")


def test_custom_user_list(tmp_path):
    store = JsonPolicyStore(str(tmp_path))
    catalog = CatalogService(_FakeClient({"WetlabDB": ["Custom"]}))
    authz = AuthorizationService(store, catalog)
    authz._store.upsert(
        CollectionAccessPolicy(
            database="WetlabDB",
            collection="Custom",
            visibility="custom",
            custom_users=["alice"],
            student_access="viewer",
            employee_access="editor",
        )
    )
    alice = User(username="alice", password_hash="x", admin=False, kind="student")
    bob = User(username="bob", password_hash="x", admin=False, kind="student")

    assert authz.can_view(alice, "WetlabDB", "Custom")
    assert not authz.can_view(bob, "WetlabDB", "Custom")
