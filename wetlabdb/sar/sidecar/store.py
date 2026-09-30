"""Sidecar persistence for SAR alignment projects (Slice 6)."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from wetlabdb.sar.hardening.completion import strip_certificate_from_draft
from wetlabdb.storage.base import StorageClientProto
from wetlabdb.storage.ids import new_local_id

META_DATABASE = "wetlabdb_meta"
PROJECTS_COLLECTION = "sar_alignment_projects"
LOCAL_RELATIVE = os.path.join(".wetlabdb", "sar_alignment_projects.json")


class SidecarConcurrencyError(ValueError):
    """Optimistic concurrency or approved-layout guard."""


class SidecarNotFoundError(LookupError):
    pass


@dataclass
class AlignmentProject:
    id: str
    version: int
    owner: str
    project_id: str
    series_id: str
    compound_ids: list[str]
    assay_ids: list[str]
    reference_id: str
    mode: str
    core_smarts: str
    snapshot_revision: str
    draft_solution: dict[str, Any]
    approval: dict[str, Any] | None
    audit: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "version": self.version,
            "owner": self.owner,
            "project_id": self.project_id,
            "series_id": self.series_id,
            "compound_ids": self.compound_ids,
            "assay_ids": self.assay_ids,
            "reference_id": self.reference_id,
            "mode": self.mode,
            "core_smarts": self.core_smarts,
            "snapshot_revision": self.snapshot_revision,
            "draft_solution": self.draft_solution,
            "approval": self.approval,
            "audit": self.audit,
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> AlignmentProject:
        return cls(
            id=str(row["_id"]),
            version=int(row.get("version") or 1),
            owner=str(row.get("owner") or ""),
            project_id=str(row.get("project_id") or ""),
            series_id=str(row.get("series_id") or ""),
            compound_ids=list(row.get("compound_ids") or []),
            assay_ids=list(row.get("assay_ids") or []),
            reference_id=str(row.get("reference_id") or ""),
            mode=str(row.get("mode") or "same_scaffold"),
            core_smarts=str(row.get("core_smarts") or "c1ccccc1"),
            snapshot_revision=str(row.get("snapshot_revision") or ""),
            draft_solution=dict(row.get("draft_solution") or {}),
            approval=row.get("approval"),
            audit=list(row.get("audit") or []),
        )


class AlignmentProjectStore(Protocol):
    def create(self, project: AlignmentProject) -> AlignmentProject: ...

    def get(self, project_id: str) -> AlignmentProject | None: ...

    def list(
        self,
        *,
        owner: str | None = None,
        project_id: str | None = None,
        series_id: str | None = None,
    ) -> list[AlignmentProject]: ...

    def update(self, project: AlignmentProject, *, expected_version: int) -> AlignmentProject: ...


def _matches_list_filters(
    row: dict[str, Any],
    *,
    owner: str | None,
    project_id: str | None,
    series_id: str | None,
) -> bool:
    if owner and str(row.get("owner") or "") != owner:
        return False
    if project_id and str(row.get("project_id") or "") != project_id:
        return False
    if series_id and str(row.get("series_id") or "") != series_id:
        return False
    return True


def last_audit_at(project: AlignmentProject) -> str:
    if not project.audit:
        return ""
    return str(project.audit[-1].get("at") or "")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JsonAlignmentProjectStore:
    def __init__(self, data_dir: str) -> None:
        self.path = os.path.join(data_dir, LOCAL_RELATIVE)
        self._lock = threading.Lock()

    def _load(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return []
        return data if isinstance(data, list) else []

    def _save(self, rows: list[dict]) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2)
        os.replace(tmp, self.path)

    def create(self, project: AlignmentProject) -> AlignmentProject:
        with self._lock:
            rows = self._load()
            rows.append(project.to_dict())
            self._save(rows)
        return project

    def get(self, project_id: str) -> AlignmentProject | None:
        for row in self._load():
            if str(row.get("_id")) == project_id:
                return AlignmentProject.from_dict(row)
        return None

    def list(
        self,
        *,
        owner: str | None = None,
        project_id: str | None = None,
        series_id: str | None = None,
    ) -> list[AlignmentProject]:
        return [
            AlignmentProject.from_dict(row)
            for row in self._load()
            if _matches_list_filters(row, owner=owner, project_id=project_id, series_id=series_id)
        ]

    def update(self, project: AlignmentProject, *, expected_version: int) -> AlignmentProject:
        with self._lock:
            rows = self._load()
            for i, row in enumerate(rows):
                if str(row.get("_id")) != project.id:
                    continue
                if int(row.get("version") or 0) != expected_version:
                    raise SidecarConcurrencyError("project version mismatch")
                rows[i] = project.to_dict()
                self._save(rows)
                return project
        raise SidecarNotFoundError(project.id)


class MongoAlignmentProjectStore:
    def __init__(self, client: StorageClientProto) -> None:
        self._coll = client[META_DATABASE][PROJECTS_COLLECTION]

    def create(self, project: AlignmentProject) -> AlignmentProject:
        self._coll.insert_one(project.to_dict())
        return project

    def get(self, project_id: str) -> AlignmentProject | None:
        row = self._coll.find_one({"_id": project_id})
        return AlignmentProject.from_dict(row) if row else None

    def list(
        self,
        *,
        owner: str | None = None,
        project_id: str | None = None,
        series_id: str | None = None,
    ) -> list[AlignmentProject]:
        filt: dict[str, Any] = {}
        if owner:
            filt["owner"] = owner
        if project_id:
            filt["project_id"] = project_id
        if series_id:
            filt["series_id"] = series_id
        return [AlignmentProject.from_dict(row) for row in self._coll.find(filt or None)]

    def update(self, project: AlignmentProject, *, expected_version: int) -> AlignmentProject:
        result = self._coll.update_one(
            {"_id": project.id, "version": expected_version},
            {"$set": project.to_dict()},
        )
        if result.matched_count == 0:
            existing = self.get(project.id)
            if existing is None:
                raise SidecarNotFoundError(project.id)
            raise SidecarConcurrencyError("project version mismatch")
        return project


class SarAlignmentSidecar:
    """High-level alignment project + approval operations."""

    def __init__(self, store: AlignmentProjectStore) -> None:
        self._store = store

    @classmethod
    def from_settings(cls, *, is_local: bool, data_dir: str, client: StorageClientProto) -> SarAlignmentSidecar:
        if is_local:
            store: AlignmentProjectStore = JsonAlignmentProjectStore(data_dir)
        else:
            store = MongoAlignmentProjectStore(client)
        return cls(store)

    def create_project(
        self,
        *,
        owner: str,
        project_id: str,
        series_id: str,
        compound_ids: list[str],
        assay_ids: list[str],
        reference_id: str,
        mode: str,
        core_smarts: str,
        snapshot_revision: str,
        draft_solution: dict[str, Any],
    ) -> AlignmentProject:
        pid = new_local_id()
        project = AlignmentProject(
            id=pid,
            version=1,
            owner=owner,
            project_id=project_id,
            series_id=series_id,
            compound_ids=compound_ids,
            assay_ids=assay_ids,
            reference_id=reference_id,
            mode=mode,
            core_smarts=core_smarts,
            snapshot_revision=snapshot_revision,
            draft_solution=draft_solution,
            approval=None,
            audit=[{"action": "create", "at": _utc_now(), "by": owner}],
        )
        return self._store.create(project)

    def get_project(self, project_id: str) -> AlignmentProject:
        project = self._store.get(project_id)
        if project is None:
            raise SidecarNotFoundError(project_id)
        return project

    def list_projects(
        self,
        *,
        owner: str | None = None,
        project_id: str | None = None,
        series_id: str | None = None,
        limit: int = 12,
    ) -> list[AlignmentProject]:
        items = self._store.list(owner=owner, project_id=project_id, series_id=series_id)
        items.sort(key=last_audit_at, reverse=True)
        return items[: max(0, limit)]

    def patch_draft(
        self,
        project_id: str,
        *,
        expected_version: int,
        actor: str,
        draft_solution: dict[str, Any],
        snapshot_revision: str | None = None,
        force_unapproved_edit: bool = False,
    ) -> AlignmentProject:
        project = self.get_project(project_id)
        if project.version != expected_version:
            raise SidecarConcurrencyError("project version mismatch")
        if project.approval is not None and not force_unapproved_edit:
            if snapshot_revision is None or snapshot_revision == project.snapshot_revision:
                raise SidecarConcurrencyError(
                    "approved layout locked — refresh snapshot or fork before editing"
                )
        if draft_solution != project.draft_solution and project.draft_solution.get("certificate"):
            draft_solution = strip_certificate_from_draft(draft_solution)
        next_rev = snapshot_revision or project.snapshot_revision
        approval = None if snapshot_revision and snapshot_revision != project.snapshot_revision else project.approval
        if project.approval and approval is None:
            project.audit.append(
                {"action": "approval_cleared_revision", "at": _utc_now(), "by": actor}
            )
        updated = AlignmentProject(
            id=project.id,
            version=project.version + 1,
            owner=project.owner,
            project_id=project.project_id,
            series_id=project.series_id,
            compound_ids=project.compound_ids,
            assay_ids=project.assay_ids,
            reference_id=project.reference_id,
            mode=project.mode,
            core_smarts=project.core_smarts,
            snapshot_revision=next_rev,
            draft_solution=draft_solution,
            approval=approval,
            audit=[
                *project.audit,
                {"action": "patch_draft", "at": _utc_now(), "by": actor},
            ],
        )
        return self._store.update(updated, expected_version=expected_version)

    def approve(
        self,
        project_id: str,
        *,
        expected_version: int,
        actor: str,
        snapshot_revision: str,
    ) -> AlignmentProject:
        project = self.get_project(project_id)
        if project.version != expected_version:
            raise SidecarConcurrencyError("project version mismatch")
        if snapshot_revision != project.snapshot_revision:
            raise SidecarConcurrencyError(
                "source revision mismatch — refresh snapshot before approval"
            )
        if project.draft_solution.get("status") not in ("OPTIMAL", "VALID"):
            raise SidecarConcurrencyError("cannot approve non-valid draft solution")
        updated = AlignmentProject(
            id=project.id,
            version=project.version + 1,
            owner=project.owner,
            project_id=project.project_id,
            series_id=project.series_id,
            compound_ids=project.compound_ids,
            assay_ids=project.assay_ids,
            reference_id=project.reference_id,
            mode=project.mode,
            core_smarts=project.core_smarts,
            snapshot_revision=project.snapshot_revision,
            draft_solution=project.draft_solution,
            approval={
                "solution_version": project.version,
                "snapshot_revision": snapshot_revision,
                "approved_at": _utc_now(),
                "approved_by": actor,
            },
            audit=[
                *project.audit,
                {"action": "approve", "at": _utc_now(), "by": actor},
            ],
        )
        return self._store.update(updated, expected_version=expected_version)


__all__ = [
    "AlignmentProject",
    "SarAlignmentSidecar",
    "SidecarConcurrencyError",
    "SidecarNotFoundError",
    "last_audit_at",
]
