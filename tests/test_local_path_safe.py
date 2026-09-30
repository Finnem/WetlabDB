"""Local storage path containment."""

from __future__ import annotations

import pytest

from wetlabdb.services.catalog_names import InvalidCatalogNameError
from wetlabdb.storage.local import LocalClient


def test_local_client_rejects_parent_database_name(tmp_path):
    client = LocalClient(str(tmp_path))
    with pytest.raises(InvalidCatalogNameError):
        _ = client[".."]


def test_local_client_valid_database_stays_under_root(tmp_path):
    root = tmp_path / "data"
    client = LocalClient(str(root))
    db = client["SafeDB"]
    db.create_collection("Rows")
    assert (root / "SafeDB" / "Rows.json").is_file()
    assert not (tmp_path / "Rows.json").exists()
