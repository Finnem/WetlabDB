"""Filesystem path helpers for local JSON storage."""

from __future__ import annotations

import os

from wetlabdb.services.catalog_names import InvalidCatalogNameError, validate_catalog_name


class PathEscapeError(ValueError):
    """Resolved path would leave the configured data root."""


def assert_path_contained(resolved_path: str, root_dir: str) -> str:
    """Ensure ``resolved_path`` is inside ``root_dir`` (both real paths)."""
    resolved = os.path.realpath(resolved_path)
    root = os.path.realpath(root_dir)
    try:
        common = os.path.commonpath([resolved, root])
    except ValueError as exc:
        raise PathEscapeError("Invalid path") from exc
    if common != root:
        raise PathEscapeError("Path escapes data directory")
    return resolved


def safe_database_dir(root_dir: str, database: str) -> str:
    name = validate_catalog_name(database, kind="database")
    joined = os.path.join(root_dir, name)
    return assert_path_contained(joined, root_dir)


def safe_collection_file(db_dir: str, root_dir: str, collection: str) -> str:
    name = validate_catalog_name(collection, kind="collection")
    joined = os.path.join(db_dir, f"{name}.json")
    assert_path_contained(db_dir, root_dir)
    return assert_path_contained(joined, root_dir)


__all__ = [
    "PathEscapeError",
    "assert_path_contained",
    "safe_collection_file",
    "safe_database_dir",
]
