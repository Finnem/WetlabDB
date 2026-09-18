"""Standalone JSON-file backend.

Layout on disk::

    <data_dir>/
        <database_name>/
            <collection_name>.json   # JSON list of document dicts

Each document gets a string ``_id`` (24-char hex, format-compatible with
``bson.ObjectId``) when inserted without one. Filters are simple equality
dicts; ``$set`` and ``$unset`` are the only update operators implemented
because they are the only ones the application uses.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from wetlabdb.storage.base import (
    DeleteResult,
    InsertResult,
    UpdateResult,
)
from wetlabdb.storage.ids import new_local_id
from wetlabdb.storage.json_codec import local_json_default

# Process-local locks so concurrent requests in a single uvicorn worker cannot
# clobber each other's read-modify-write of the same JSON collection file.
_FILE_LOCKS: dict[str, threading.Lock] = {}
_FILE_LOCKS_GUARD = threading.Lock()


def _lock_for(path: str) -> threading.Lock:
    key = os.path.abspath(path)
    with _FILE_LOCKS_GUARD:
        return _FILE_LOCKS.setdefault(key, threading.Lock())


def default_local_data_dir() -> str:
    """Folder used for standalone mode when the user doesn't pick another."""
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)
    else:
        # Anchor next to the project root so users find the folder easily.
        base_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
    return os.path.join(base_dir, "local_data")


class LocalCollection:
    """JSON-file backed stand-in for ``pymongo.Collection``."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    @contextmanager
    def _locked(self) -> Iterator[None]:
        with _lock_for(self.file_path):
            yield

    # ---- Persistence ------------------------------------------------------

    def _load(self) -> list[dict]:
        if not os.path.exists(self.file_path):
            return []
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
        return data if isinstance(data, list) else []

    def _save(self, docs: list[dict]) -> None:
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        tmp_path = self.file_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(docs, f, indent=2, default=local_json_default)
        os.replace(tmp_path, self.file_path)

    # ---- Filter matching --------------------------------------------------

    @staticmethod
    def _matches(doc: dict, filt: dict | None) -> bool:
        if not filt:
            return True
        for key, expected in filt.items():
            actual = doc.get(key)
            if key == "_id":
                if str(actual) != str(expected):
                    return False
            else:
                if actual != expected:
                    return False
        return True

    # ---- Public pymongo-like API ------------------------------------------

    def find(self, filter: dict | None = None) -> list[dict]:
        with self._locked():
            docs = self._load()
        if not filter:
            return list(docs)
        return [d for d in docs if self._matches(d, filter)]

    def find_one(self, filter: dict | None = None) -> dict | None:
        with self._locked():
            docs = self._load()
        for doc in docs:
            if self._matches(doc, filter):
                return doc
        return None

    def insert_one(self, document: dict) -> InsertResult:
        with self._locked():
            docs = self._load()
            doc = dict(document)
            if "_id" not in doc or doc["_id"] in (None, ""):
                doc["_id"] = new_local_id()
            else:
                doc["_id"] = str(doc["_id"])
            docs.append(doc)
            self._save(docs)
            return InsertResult(inserted_id=doc["_id"])

    def update_one(self, filter: dict, update: dict) -> UpdateResult:
        with self._locked():
            docs = self._load()
            for doc in docs:
                if self._matches(doc, filter):
                    if "$set" in update:
                        for k, v in update["$set"].items():
                            doc[k] = v
                    if "$unset" in update:
                        for k in update["$unset"]:
                            doc.pop(k, None)
                    self._save(docs)
                    return UpdateResult(matched_count=1, modified_count=1)
            return UpdateResult(matched_count=0, modified_count=0)

    def delete_one(self, filter: dict) -> DeleteResult:
        with self._locked():
            docs = self._load()
            for i, doc in enumerate(docs):
                if self._matches(doc, filter):
                    docs.pop(i)
                    self._save(docs)
                    return DeleteResult(deleted_count=1)
            return DeleteResult(deleted_count=0)

    def count_documents(self, filter: dict | None = None) -> int:
        return len(self.find(filter))


class LocalDatabase:
    """Filesystem folder treated as a database of JSON collections."""

    def __init__(self, db_dir: str) -> None:
        self.db_dir = db_dir

    def __getitem__(self, name: str) -> LocalCollection:
        return LocalCollection(os.path.join(self.db_dir, f"{name}.json"))

    def list_collection_names(self) -> list[str]:
        if not os.path.isdir(self.db_dir):
            return []
        return sorted(
            os.path.splitext(f)[0]
            for f in os.listdir(self.db_dir)
            if f.endswith(".json") and not f.endswith(".tmp")
        )

    def create_collection(self, name: str) -> LocalCollection:
        os.makedirs(self.db_dir, exist_ok=True)
        path = os.path.join(self.db_dir, f"{name}.json")
        if os.path.exists(path):
            raise ValueError(f"Collection '{name}' already exists")
        with open(path, "w", encoding="utf-8") as f:
            json.dump([], f)
        return LocalCollection(path)

    def drop_collection(self, name: str) -> None:
        path = os.path.join(self.db_dir, f"{name}.json")
        if os.path.exists(path):
            os.remove(path)


class LocalClient:
    """File-backed stand-in for ``pymongo.MongoClient``."""

    def __init__(self, root_dir: str) -> None:
        self.root_dir = root_dir
        os.makedirs(self.root_dir, exist_ok=True)

    def __getitem__(self, name: str) -> LocalDatabase:
        return LocalDatabase(os.path.join(self.root_dir, name))

    def list_database_names(self) -> list[str]:
        if not os.path.isdir(self.root_dir):
            return []
        return sorted(
            d
            for d in os.listdir(self.root_dir)
            if os.path.isdir(os.path.join(self.root_dir, d))
        )

    def drop_database(self, name: str) -> None:
        path = os.path.join(self.root_dir, name)
        if os.path.isdir(path):
            shutil.rmtree(path)

    def close(self) -> None:  # pragma: no cover - no-op for compatibility
        pass


def get_local_client(
    data_dir: str | None = None,
    bootstrap_db: str | None = "WetlabDB",
    bootstrap_collection: str | None = "Compounds",
) -> LocalClient:
    """Create a standalone client backed by JSON files.

    On first launch (empty ``data_dir``) a default database/collection is
    created so the UI has something to show. Pass ``bootstrap_db=None`` to
    disable that behaviour (used in tests).
    """
    if not data_dir:
        data_dir = default_local_data_dir()
    client = LocalClient(data_dir)
    if bootstrap_db and not client.list_database_names():
        db = client[bootstrap_db]
        if (
            bootstrap_collection
            and bootstrap_collection not in db.list_collection_names()
        ):
            db.create_collection(bootstrap_collection)
    return client


__all__ = [
    "LocalClient",
    "LocalCollection",
    "LocalDatabase",
    "default_local_data_dir",
    "get_local_client",
]
