"""Top-level package for the WetlabDB compound database application.

The package is organised in layers:

* :mod:`wetlabdb.storage`  -- pluggable document store (local JSON or MongoDB)
* :mod:`wetlabdb.chem`     -- pure RDKit chemistry helpers
* :mod:`wetlabdb.services` -- application services that compose storage + chem
* :mod:`wetlabdb.api`      -- FastAPI HTTP API for the hosted web UI
* :mod:`wetlabdb.schema`   -- shared compound form schema
* :mod:`wetlabdb.ui`       -- legacy Tkinter user interface (``--tk``)
* :mod:`wetlabdb.config`   -- persisted desktop application configuration
"""

__version__ = "0.3.0"
