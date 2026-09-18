"""Application service layer.

Services are pure-Python classes that orchestrate :mod:`wetlabdb.storage` and
:mod:`wetlabdb.chem` for the UI. They contain no Tk references, which makes
them straightforward to test and easy to reuse from non-GUI scripts.
"""

from __future__ import annotations

from wetlabdb.services.auth import AuthError, AuthService, User
from wetlabdb.services.catalog import CatalogError, CatalogService
from wetlabdb.services.compounds import CompoundService
from wetlabdb.services.csv_io import (
    CsvImportSummary,
    alternative_field,
    export_csv,
    export_csv_text,
    import_csv,
)
from wetlabdb.services.search import SearchService

__all__ = [
    "AuthError",
    "AuthService",
    "CatalogError",
    "CatalogService",
    "CompoundService",
    "CsvImportSummary",
    "SearchService",
    "alternative_field",
    "User",
    "export_csv",
    "export_csv_text",
    "import_csv",
]
