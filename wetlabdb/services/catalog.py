"""Database / collection administration over a :class:`StorageClientProto`."""

from __future__ import annotations

from wetlabdb.services.catalog_names import InvalidCatalogNameError, validate_catalog_name
from wetlabdb.storage.base import CollectionProto, StorageClientProto

# Names the web UI must never offer as compound databases.
HIDDEN_DATABASE_NAMES: frozenset[str] = frozenset(
    {"wetlabdb_meta", "admin", "local", "config"}
)


def is_hidden_database(name: str) -> bool:
    """Return True for internal / system databases (and dotted folders)."""
    if not name or name.startswith("."):
        return True
    return name in HIDDEN_DATABASE_NAMES


class CatalogError(ValueError):
    """Invalid catalog operation (duplicate name, hidden target, ...)."""


class CatalogService:
    """List / create / drop databases and collections."""

    def __init__(self, client: StorageClientProto) -> None:
        self._client = client

    @staticmethod
    def _validated_db(name: str) -> str:
        try:
            name = validate_catalog_name(name, kind="database")
        except InvalidCatalogNameError as exc:
            raise CatalogError(str(exc)) from exc
        if is_hidden_database(name):
            raise CatalogError(f"Database name '{name}' is reserved")
        return name

    @staticmethod
    def _validated_collection(name: str) -> str:
        try:
            return validate_catalog_name(name, kind="collection")
        except InvalidCatalogNameError as exc:
            raise CatalogError(str(exc)) from exc

    def list_databases(self) -> list[str]:
        return sorted(
            name
            for name in self._client.list_database_names()
            if not is_hidden_database(name)
        )

    def create_database(self, name: str, collection: str) -> None:
        name = self._validated_db(name)
        collection = self._validated_collection(collection)
        if name in self.list_databases():
            raise CatalogError(f"Database '{name}' already exists")
        self._client[name].create_collection(collection)

    def drop_database(self, name: str) -> None:
        name = self._validated_db(name)
        self._client.drop_database(name)

    def list_collections(self, database: str) -> list[str]:
        database = self._validated_db(database)
        self._require_visible(database)
        return list(self._client[database].list_collection_names())

    def create_collection(self, database: str, name: str) -> None:
        database = self._validated_db(database)
        self._require_visible(database)
        name = self._validated_collection(name)
        db = self._client[database]
        if name in db.list_collection_names():
            raise CatalogError(f"Collection '{name}' already exists")
        db.create_collection(name)

    def drop_collection(self, database: str, name: str) -> None:
        database = self._validated_db(database)
        self._require_visible(database)
        name = self._validated_collection(name)
        self._client[database].drop_collection(name)

    def collection(self, database: str, name: str) -> CollectionProto:
        database = self._validated_db(database)
        self._require_visible(database)
        name = self._validated_collection(name)
        return self._client[database][name]

    def _require_visible(self, database: str) -> None:
        if is_hidden_database(database):
            raise CatalogError(f"Database '{database}' is not available")


__all__ = [
    "HIDDEN_DATABASE_NAMES",
    "CatalogError",
    "CatalogService",
    "is_hidden_database",
]
