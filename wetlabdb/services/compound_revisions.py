"""Store last-N compound document revisions for recovery."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from typing import Any, Protocol

from wetlabdb.services.auth import META_DATABASE
from wetlabdb.services.compound_meta import without_meta_fields, utc_now_iso
from wetlabdb.settings import Settings
from wetlabdb.storage.base import CollectionProto, StorageClientProto
from wetlabdb.storage.json_codec import MongoJSONEncoder

MAX_COMPOUND_REVISIONS = 10
REVISIONS_COLLECTION = "compound_document_revisions"
LOCAL_REVISIONS_RELATIVE = os.path.join(".wetlabdb", "compound_revisions.json")


def revision_key(database: str, collection: str, doc_id: str) -> str:
    return f"{database}/{collection}/{doc_id}"


@dataclass
class CompoundRevision:
    at: str
    actor: str
    document: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"at": self.at, "actor": self.actor, "document": self.document}


class RevisionStore(Protocol):
    def list_revisions(self, key: str) -> list[CompoundRevision]: ...

    def push(self, key: str, revision: CompoundRevision) -> None: ...


class JsonRevisionStore:
    def __init__(self, data_dir: str) -> None:
        self._path = os.path.join(data_dir, LOCAL_REVISIONS_RELATIVE)
        self._lock = threading.Lock()

    def _load(self) -> dict[str, list[dict]]:
        if not os.path.exists(self._path):
            return {}
        try:
            with open(self._path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, rows: dict[str, list[dict]]) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(rows, handle, indent=2, default=str)
        os.replace(tmp, self._path)

    def list_revisions(self, key: str) -> list[CompoundRevision]:
        rows = self._load().get(key, [])
        return [
            CompoundRevision(
                at=str(r.get("at") or ""),
                actor=str(r.get("actor") or ""),
                document=dict(r.get("document") or {}),
            )
            for r in rows
        ]

    def push(self, key: str, revision: CompoundRevision) -> None:
        with self._lock:
            data = self._load()
            history = list(data.get(key, []))
            history.append(revision.to_dict())
            data[key] = history[-MAX_COMPOUND_REVISIONS:]
            self._save(data)


class MongoRevisionStore:
    def __init__(self, client: StorageClientProto) -> None:
        self._coll: CollectionProto = client[META_DATABASE][REVISIONS_COLLECTION]

    def list_revisions(self, key: str) -> list[CompoundRevision]:
        row = self._coll.find_one({"key": key})
        if not row:
            return []
        out: list[CompoundRevision] = []
        for r in row.get("revisions") or []:
            out.append(
                CompoundRevision(
                    at=str(r.get("at") or ""),
                    actor=str(r.get("actor") or ""),
                    document=dict(r.get("document") or {}),
                )
            )
        return out

    def push(self, key: str, revision: CompoundRevision) -> None:
        row = self._coll.find_one({"key": key})
        history = list((row or {}).get("revisions") or [])
        history.append(revision.to_dict())
        trimmed = history[-MAX_COMPOUND_REVISIONS:]
        payload = {"key": key, "revisions": trimmed}
        if row:
            self._coll.update_one({"key": key}, {"$set": payload})
        else:
            self._coll.insert_one(payload)


class CompoundRevisionService:
    def __init__(self, store: RevisionStore) -> None:
        self._store = store

    def record_snapshot(
        self,
        *,
        database: str,
        collection: str,
        doc_id: str,
        actor: str,
        document: dict,
    ) -> None:
        snapshot = json.loads(json.dumps(without_meta_fields(document), cls=MongoJSONEncoder))
        if "_id" in snapshot:
            snapshot["_id"] = str(snapshot["_id"])
        self._store.push(
            revision_key(database, collection, doc_id),
            CompoundRevision(at=utc_now_iso(), actor=actor, document=snapshot),
        )

    def list_for(self, database: str, collection: str, doc_id: str) -> list[dict]:
        key = revision_key(database, collection, doc_id)
        return [r.to_dict() for r in self._store.list_revisions(key)]


def revision_store_for(settings: Settings, client: StorageClientProto) -> RevisionStore:
    if settings.is_local:
        return JsonRevisionStore(settings.data_dir)
    return MongoRevisionStore(client)


__all__ = [
    "CompoundRevisionService",
    "MAX_COMPOUND_REVISIONS",
    "revision_store_for",
]
