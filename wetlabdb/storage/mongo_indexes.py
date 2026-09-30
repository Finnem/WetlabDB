"""Ensure recommended MongoDB indexes in remote deployments."""

from __future__ import annotations

import logging

from wetlabdb.services.auth import META_DATABASE
from wetlabdb.services.compound_meta import DELETED_AT
from wetlabdb.settings import Settings
from wetlabdb.storage.base import StorageClientProto
from wetlabdb.storage.mongo import MongoClientAdapter

_log = logging.getLogger("wetlabdb.lifecycle")

_COMPOUND_INDEX_FIELDS = ("Name", "CAS Nr", "SMILES")


def ensure_deployment_indexes(settings: Settings, client: StorageClientProto) -> None:
    """Create idempotent indexes for production MongoDB (no-op for local JSON / mocks)."""
    if settings.is_local:
        return
    if not isinstance(client, MongoClientAdapter):
        return

    raw = client._raw  # noqa: SLF001 — deployment hook only
    try:
        _ensure_meta_indexes(raw[META_DATABASE])
        for db_name in raw.list_database_names():
            if db_name.startswith("wetlabdb") or db_name == META_DATABASE:
                continue
            db = raw[db_name]
            for coll_name in db.list_collection_names():
                _ensure_compound_indexes(db[coll_name])
    except Exception as exc:
        _log.warning('{"event":"indexes.error","detail":"%s"}', str(exc))


def _ensure_compound_indexes(raw_coll) -> None:
    if type(raw_coll).__module__.startswith("mongomock"):
        return
    raw_coll.create_index([(DELETED_AT, 1)], sparse=True, name="wetlabdb_deleted_at_sparse")
    for field in _COMPOUND_INDEX_FIELDS:
        raw_coll.create_index([(field, 1)], name=f"wetlabdb_{field.replace(' ', '_')}")


def _ensure_meta_indexes(raw_db) -> None:
    if type(raw_db).__module__.startswith("mongomock"):
        return
    from wetlabdb.services.audit import AUDIT_COLLECTION
    from wetlabdb.services.authorization import POLICIES_COLLECTION

    raw_db["users"].create_index([("username", 1)], unique=True, name="wetlabdb_username_unique")
    raw_db[AUDIT_COLLECTION].create_index([("at", -1)], name="wetlabdb_audit_at")
    raw_db[POLICIES_COLLECTION].create_index(
        [("database", 1), ("collection", 1)],
        unique=True,
        name="wetlabdb_policy_db_coll",
    )


__all__ = ["ensure_deployment_indexes"]
