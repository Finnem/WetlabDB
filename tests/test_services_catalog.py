"""Tests for :class:`wetlabdb.services.CatalogService`."""

from __future__ import annotations

import pytest

from wetlabdb.services.catalog import CatalogError, CatalogService, HIDDEN_DATABASE_NAMES
from wetlabdb.storage import get_local_client


@pytest.fixture
def catalog(tmp_path):
    client = get_local_client(str(tmp_path), bootstrap_db=None)
    return CatalogService(client)


def test_hidden_names_filtered(catalog, tmp_path):
    catalog.create_database("WetlabDB", "Compounds")
    # Simulate a meta folder / dotted dir that must not be listed.
    (tmp_path / "wetlabdb_meta").mkdir()
    (tmp_path / ".wetlabdb").mkdir()
    names = catalog.list_databases()
    assert "WetlabDB" in names
    for hidden in HIDDEN_DATABASE_NAMES:
        assert hidden not in names
    assert ".wetlabdb" not in names


def test_create_and_drop_round_trip(catalog):
    catalog.create_database("Lib", "A")
    assert "Lib" in catalog.list_databases()
    assert "A" in catalog.list_collections("Lib")
    catalog.create_collection("Lib", "B")
    catalog.drop_collection("Lib", "B")
    assert "B" not in catalog.list_collections("Lib")
    catalog.drop_database("Lib")
    assert "Lib" not in catalog.list_databases()


def test_reserved_name_rejected(catalog):
    with pytest.raises(CatalogError):
        catalog.create_database("admin", "x")
