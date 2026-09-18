"""WetlabDB launcher / backwards-compatible shim.

The application now lives in the :mod:`wetlabdb` package. This file is kept
as a thin entry point so that:

* the existing PyInstaller spec (which targets ``wetlabDB.py``) keeps building;
* anyone who runs ``python wetlabDB.py`` still launches the app.

Importing names from this module (e.g. ``from wetlabDB import LocalClient``)
also keeps working via the re-exports below, so any external scripts that
used the monolith won't break.
"""

from __future__ import annotations

# Re-exports kept for backwards compatibility with code that imported names
# from the old monolithic ``wetlabDB.py``. New code should import from the
# subpackages directly (see ``wetlabdb.storage``, ``wetlabdb.chem``, etc.).
from wetlabdb.chem import enumerate_molecules_from_smarts  # noqa: F401
from wetlabdb.config import AppConfig, CONFIG_FILENAME  # noqa: F401
from wetlabdb.services import (  # noqa: F401
    CompoundService,
    SearchService,
    export_csv,
    import_csv,
)
from wetlabdb.storage import (  # noqa: F401
    LocalClient,
    LocalCollection,
    LocalDatabase,
    MongoJSONEncoder,
    ObjectId,
    PYMONGO_AVAILABLE,
    coerce_id as _coerce_id,
    default_local_data_dir as _default_local_data_dir,
    get_local_client,
    get_mongo_client,
    local_json_default as _local_json_default,
    new_local_id as _new_local_id,
)
from wetlabdb.ui import (  # noqa: F401
    ColumnSelectionDialog,
    JSONForm,
    LoginDialog,
    MolecularSearchWindow,
    MoleculeCell,
    MoleculeDrawingCanvas,
    MoleculeEditorWindow,
    MoleculeTreeview,
    MongoBrowser,
    WetlabDBApp,
    compound_form,
)
from wetlabdb.ui.app import main


if __name__ == "__main__":
    main()
