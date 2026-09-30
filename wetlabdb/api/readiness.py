"""Backend readiness checks."""

from __future__ import annotations

from fastapi import HTTPException

from wetlabdb.api.metrics import record_storage_error
from wetlabdb.settings import Settings
from wetlabdb.storage.base import StorageClientProto


def check_readiness(settings: Settings, client: StorageClientProto) -> dict:
    try:
        names = client.list_database_names()
    except Exception as exc:
        record_storage_error("readiness.list_databases")
        raise HTTPException(status_code=503, detail="Storage backend unavailable") from exc

    if settings.is_local:
        import os

        data_dir = settings.data_dir
        if not os.path.isdir(data_dir):
            raise HTTPException(status_code=503, detail="Local data directory missing")
        if not os.access(data_dir, os.R_OK | os.W_OK):
            raise HTTPException(status_code=503, detail="Local data directory not writable")

    return {
        "ok": True,
        "backend": "local_json" if settings.is_local else "mongodb",
        "database_count": len(names),
    }


__all__ = ["check_readiness"]
