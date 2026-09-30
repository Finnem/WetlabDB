"""Append-only audit log for security and data-change events."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from wetlabdb.services.auth import META_DATABASE
from wetlabdb.settings import Settings
from wetlabdb.storage.base import CollectionProto, StorageClientProto

AUDIT_COLLECTION = "audit_events"
LOCAL_AUDIT_RELATIVE = os.path.join(".wetlabdb", "audit.jsonl")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class AuditRecord:
    at: str
    actor: str | None
    action: str
    target: str
    summary: dict[str, Any]
    request_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuditStore(Protocol):
    def append(self, record: AuditRecord) -> None: ...

    def list_recent(self, *, limit: int = 100) -> list[dict[str, Any]]: ...


class JsonlAuditStore:
    """Append audit lines under the local data directory."""

    def __init__(self, data_dir: str) -> None:
        self._path = os.path.join(data_dir, LOCAL_AUDIT_RELATIVE)
        self._lock = threading.Lock()

    def append(self, record: AuditRecord) -> None:
        line = json.dumps(record.to_dict(), ensure_ascii=False, default=str) + "\n"
        with self._lock:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as handle:
                handle.write(line)

    def list_recent(self, *, limit: int = 100) -> list[dict[str, Any]]:
        if not os.path.exists(self._path):
            return []
        with self._lock:
            with open(self._path, encoding="utf-8") as handle:
                lines = handle.readlines()
        out: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return list(reversed(out))


class MongoAuditStore:
    """Persist audit rows in ``wetlabdb_meta.audit_events``."""

    def __init__(self, client: StorageClientProto) -> None:
        self._coll: CollectionProto = client[META_DATABASE][AUDIT_COLLECTION]

    def append(self, record: AuditRecord) -> None:
        self._coll.insert_one(record.to_dict())

    def list_recent(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._coll.find()
        rows.sort(key=lambda r: str(r.get("at") or ""), reverse=True)
        return rows[:limit]


class AuditService:
    def __init__(self, store: AuditStore) -> None:
        self._store = store

    def record(
        self,
        *,
        action: str,
        target: str,
        actor: str | None = None,
        summary: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> None:
        payload = dict(summary or {})
        for forbidden in ("password", "session", "secret", "token"):
            payload.pop(forbidden, None)
        self._store.append(
            AuditRecord(
                at=_utc_now(),
                actor=actor,
                action=action,
                target=target,
                summary=payload,
                request_id=request_id,
            )
        )

    def list_recent(self, *, limit: int = 100) -> list[dict[str, Any]]:
        capped = max(1, min(int(limit), 500))
        return self._store.list_recent(limit=capped)


def audit_store_for(settings: Settings, client: StorageClientProto) -> AuditStore:
    if settings.is_local:
        return JsonlAuditStore(settings.data_dir)
    return MongoAuditStore(client)


__all__ = [
    "AUDIT_COLLECTION",
    "AuditRecord",
    "AuditService",
    "audit_store_for",
]
