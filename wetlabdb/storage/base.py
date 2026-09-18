"""Storage protocol + result dataclasses.

Both :mod:`wetlabdb.storage.local` and :mod:`wetlabdb.storage.mongo` implement
the protocols defined here, which is the only thing the rest of the
application is allowed to depend on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class InsertResult:
    """Returned by :meth:`CollectionProto.insert_one`."""

    inserted_id: str


@dataclass
class UpdateResult:
    """Returned by :meth:`CollectionProto.update_one`."""

    matched_count: int
    modified_count: int


@dataclass
class DeleteResult:
    """Returned by :meth:`CollectionProto.delete_one`."""

    deleted_count: int


@runtime_checkable
class CollectionProto(Protocol):
    """A document collection: the unit the UI binds to a table."""

    def find(self, filter: dict | None = None) -> list[dict]: ...

    def find_one(self, filter: dict | None = None) -> dict | None: ...

    def insert_one(self, document: dict) -> InsertResult: ...

    def update_one(self, filter: dict, update: dict) -> UpdateResult: ...

    def delete_one(self, filter: dict) -> DeleteResult: ...

    def count_documents(self, filter: dict | None = None) -> int: ...


@runtime_checkable
class DatabaseProto(Protocol):
    """A named bucket of collections."""

    def __getitem__(self, name: str) -> CollectionProto: ...

    def list_collection_names(self) -> list[str]: ...

    def create_collection(self, name: str) -> CollectionProto: ...

    def drop_collection(self, name: str) -> None: ...


@runtime_checkable
class StorageClientProto(Protocol):
    """The entry point for either backend."""

    def __getitem__(self, name: str) -> DatabaseProto: ...

    def list_database_names(self) -> list[str]: ...

    def drop_database(self, name: str) -> None: ...

    def close(self) -> None: ...


__all__ = [
    "CollectionProto",
    "DatabaseProto",
    "DeleteResult",
    "InsertResult",
    "StorageClientProto",
    "UpdateResult",
]
