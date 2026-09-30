"""Adapter that turns a real ``pymongo.MongoClient`` into the same shape as
the :mod:`wetlabdb.storage.base` protocols.

The point of the adapter (rather than just exposing pymongo objects directly)
is normalising result types: pymongo returns its own ``InsertOneResult`` /
``UpdateResult`` / ``DeleteResult`` objects, and exposing those would mean the
service layer would have to special-case attribute names. By wrapping every
operation we guarantee that the rest of the application sees the same
:class:`~wetlabdb.storage.base.InsertResult` / :class:`UpdateResult` /
:class:`DeleteResult` dataclasses regardless of which backend is active.
"""

from __future__ import annotations

from typing import Any

from wetlabdb.storage.base import (
    DeleteResult,
    InsertResult,
    UpdateResult,
)
from wetlabdb.storage.ids import PYMONGO_AVAILABLE, coerce_id
from wetlabdb.services.compound_meta import DELETED_AT
from wetlabdb.storage.compound_queries import merge_cursor
from wetlabdb.storage.pagination import memory_find_page


def _id_equal(left, right) -> bool:
    """Compare document ids as strings so bson / mongomock ObjectIds match."""
    return str(left) == str(right)


def _matches(doc: dict, filt: dict | None) -> bool:
    if not filt:
        return True
    for key, expected in filt.items():
        actual = doc.get(key)
        if key == "_id":
            if not _id_equal(actual, expected):
                return False
        elif actual != expected:
            return False
    return True


class _MongoCollection:
    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def _prefer_memory_pagination(self) -> bool:
        return type(self._raw).__module__.startswith("mongomock")

    def find_page(
        self,
        *,
        limit: int,
        after_id: str | None = None,
        exclude_soft_deleted: bool = True,
        projection: dict | None = None,
    ) -> list[dict]:
        capped = max(1, int(limit))
        if self._prefer_memory_pagination():
            return memory_find_page(
                self.find(),
                limit=capped,
                after_id=after_id,
                exclude_soft_deleted=exclude_soft_deleted,
            )
        try:
            query: dict = {}
            if exclude_soft_deleted:
                query[DELETED_AT] = {"$exists": False}
            if after_id:
                query["_id"] = {"$gt": coerce_id(after_id)}
            kwargs: dict = {}
            if projection:
                kwargs["projection"] = projection
            cursor = self._raw.find(query, **kwargs).sort("_id", 1).limit(capped)
            return list(cursor)
        except (TypeError, NotImplementedError):
            return memory_find_page(
                self.find(),
                limit=capped,
                after_id=after_id,
                exclude_soft_deleted=exclude_soft_deleted,
            )

    def count_active_documents(self) -> int:
        if self._prefer_memory_pagination():
            return len(
                memory_find_page(self.find(), limit=10**9, exclude_soft_deleted=True)
            )
        try:
            return int(self._raw.count_documents({DELETED_AT: {"$exists": False}}))
        except (TypeError, NotImplementedError):
            return len(
                memory_find_page(self.find(), limit=10**9, exclude_soft_deleted=True)
            )

    def find(self, filter: dict | None = None) -> list[dict]:
        docs = list(self._raw.find())
        if not filter:
            return docs
        return [d for d in docs if _matches(d, filter)]

    def find_one(self, filter: dict | None = None) -> dict | None:
        for doc in self.find(filter):
            return doc
        return None

    def insert_one(self, document: dict) -> InsertResult:
        result = self._raw.insert_one(document)
        return InsertResult(inserted_id=str(result.inserted_id))

    def update_one(self, filter: dict, update: dict) -> UpdateResult:
        existing = self.find_one(filter)
        if existing is None:
            return UpdateResult(matched_count=0, modified_count=0)
        payload = dict(update)
        unset = payload.get("$unset")
        if unset is not None and not isinstance(unset, dict):
            payload["$unset"] = {key: "" for key in unset}
        result = self._raw.update_one({"_id": existing["_id"]}, payload)
        return UpdateResult(
            matched_count=int(result.matched_count),
            modified_count=int(result.modified_count),
        )

    def delete_one(self, filter: dict) -> DeleteResult:
        existing = self.find_one(filter)
        if existing is None:
            return DeleteResult(deleted_count=0)
        result = self._raw.delete_one({"_id": existing["_id"]})
        return DeleteResult(deleted_count=int(result.deleted_count))

    def supports_server_query(self) -> bool:
        return not self._prefer_memory_pagination()

    def count_documents(self, filter: dict | None = None) -> int:
        return int(self._raw.count_documents(filter or {}))

    def find_query_page(
        self,
        query: dict,
        *,
        limit: int,
        after_id: str | None = None,
        projection: dict | None = None,
    ) -> list[dict]:
        """Server-side filter + ``_id`` pagination (falls back in mongomock)."""
        capped = max(1, int(limit))
        if self._prefer_memory_pagination():
            return memory_find_page(
                self.find(),
                limit=capped,
                after_id=after_id,
                exclude_soft_deleted=True,
            )
        try:
            merged = merge_cursor(query, after_id)
            kwargs: dict = {}
            if projection:
                kwargs["projection"] = projection
            cursor = self._raw.find(merged, **kwargs).sort("_id", 1).limit(capped)
            return list(cursor)
        except (TypeError, NotImplementedError):
            return memory_find_page(
                self.find(),
                limit=capped,
                after_id=after_id,
                exclude_soft_deleted=True,
            )


class _MongoDatabase:
    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def __getitem__(self, name: str) -> _MongoCollection:
        return _MongoCollection(self._raw[name])

    def list_collection_names(self) -> list[str]:
        return list(self._raw.list_collection_names())

    def create_collection(self, name: str) -> _MongoCollection:
        return _MongoCollection(self._raw.create_collection(name))

    def drop_collection(self, name: str) -> None:
        self._raw.drop_collection(name)


class MongoClientAdapter:
    """Wrap a ``pymongo.MongoClient`` (or compatible mock) in the storage protocol."""

    def __init__(self, raw_client: Any) -> None:
        self._raw = raw_client

    def __getitem__(self, name: str) -> _MongoDatabase:
        return _MongoDatabase(self._raw[name])

    def list_database_names(self) -> list[str]:
        return list(self._raw.list_database_names())

    def drop_database(self, name: str) -> None:
        self._raw.drop_database(name)

    def close(self) -> None:
        try:
            self._raw.close()
        except Exception:  # pragma: no cover - some mocks lack ``close``
            pass


def get_mongo_client(
    host: str = "mongodb://localhost:27017",
    username: str | None = None,
    password: str | None = None,
    auth_source: str = "admin",
) -> MongoClientAdapter:
    """Connect to MongoDB and return a protocol-shaped client."""
    if not PYMONGO_AVAILABLE:
        raise RuntimeError(
            "pymongo is not installed; remote MongoDB mode is unavailable. "
            "Install it with `pip install pymongo` or use Standalone mode."
        )

    from pymongo import MongoClient  # local import keeps the module optional

    if username and password:
        raw = MongoClient(
            host=host,
            username=username,
            password=password,
            authSource=auth_source,
        )
    else:
        raw = MongoClient(host)
    return MongoClientAdapter(raw)


__all__ = ["MongoClientAdapter", "get_mongo_client"]
