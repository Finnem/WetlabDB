"""Unit tests for catalog identifier validation."""

from __future__ import annotations

import pytest

from wetlabdb.services.catalog_names import InvalidCatalogNameError, validate_catalog_name


@pytest.mark.parametrize(
    "name",
    ["WetlabDB", "Compounds", "ScratchDB", "a-b_c", "A1"],
)
def test_validate_accepts_safe_names(name: str):
    assert validate_catalog_name(name, kind="database") == name
    assert validate_catalog_name(name, kind="collection") == name


@pytest.mark.parametrize(
    "name",
    ["", " ", "..", ".", "../x", "a/../../b", "bad/name", "bad\\name", "has space"],
)
def test_validate_rejects_unsafe_names(name: str):
    with pytest.raises(InvalidCatalogNameError):
        validate_catalog_name(name, kind="database")


def test_validate_rejects_overlong_name():
    with pytest.raises(InvalidCatalogNameError):
        validate_catalog_name("x" * 65, kind="collection")
