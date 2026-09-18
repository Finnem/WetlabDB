"""Pluggable document-store layer.

Two backends are provided behind a common :mod:`Protocol <typing>`:

* :class:`~wetlabdb.storage.local.LocalClient` -- JSON files on disk, no
  external service required.
* :class:`~wetlabdb.storage.mongo.MongoClientAdapter` -- a thin wrapper around
  ``pymongo.MongoClient`` that normalises result types so they match the local
  backend.

The public API is intentionally narrow: it implements only the slice of the
PyMongo surface area that the application actually uses.
"""

from __future__ import annotations

from wetlabdb.storage.base import (
    CollectionProto,
    DatabaseProto,
    DeleteResult,
    InsertResult,
    StorageClientProto,
    UpdateResult,
)
from wetlabdb.storage.ids import (
    PYMONGO_AVAILABLE,
    ObjectId,
    coerce_id,
    new_local_id,
)
from wetlabdb.storage.json_codec import (
    MongoJSONEncoder,
    local_json_default,
)
from wetlabdb.storage.local import (
    LocalClient,
    LocalCollection,
    LocalDatabase,
    default_local_data_dir,
    get_local_client,
)

__all__ = [
    "CollectionProto",
    "DatabaseProto",
    "DeleteResult",
    "InsertResult",
    "LocalClient",
    "LocalCollection",
    "LocalDatabase",
    "MongoJSONEncoder",
    "ObjectId",
    "PYMONGO_AVAILABLE",
    "StorageClientProto",
    "UpdateResult",
    "coerce_id",
    "default_local_data_dir",
    "get_local_client",
    "local_json_default",
    "new_local_id",
]


def get_mongo_client(
    host: str = "mongodb://localhost:27017",
    username: str | None = None,
    password: str | None = None,
    auth_source: str = "admin",
):
    """Return a Mongo-backed :class:`StorageClientProto`.

    Imported lazily so that environments without ``pymongo`` installed can
    still use the standalone backend.
    """
    from wetlabdb.storage.mongo import get_mongo_client as _impl

    return _impl(host, username, password, auth_source)
