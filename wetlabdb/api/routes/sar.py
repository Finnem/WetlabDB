"""SAR Alignment read API (database-connected selection)."""

from __future__ import annotations

import json
import queue
import threading

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from wetlabdb.api.deps import get_catalog, get_current_user
from wetlabdb.services.authorization import AuthorizationService
from wetlabdb.schema.compound import COMPOUND_FORM
from wetlabdb.services.auth import User
from wetlabdb.services.catalog import CatalogService
from wetlabdb.sar.pipeline.live import result_to_response, run_from_snapshot
from wetlabdb.sar.hardening.limits import (
    ALIGNMENT_RUN_TIMEOUT_SECONDS,
    BENCHMARK_COMPOUND_COUNTS,
    LIVE_ALIGN_MAX_COMPOUNDS,
    MAX_ALIGNMENT_COMPOUNDS,
    MAX_OPTIMIZER_TIME_SECONDS,
)
from wetlabdb.sar.hardening.vocabulary import STATUS_CASE_MESSAGES
from wetlabdb.sar.repository import SarRepositoryError, WetlabDBCompoundRepository
from wetlabdb.sar.repository import list_assay_field_ids, parse_unit_from_field_name
from wetlabdb.sar.sidecar import AlignmentProject, SarAlignmentSidecar, SidecarConcurrencyError, SidecarNotFoundError
from wetlabdb.sar.sidecar.store import last_audit_at

router = APIRouter(tags=["sar"])


def get_sar_repo(catalog: CatalogService = Depends(get_catalog)) -> WetlabDBCompoundRepository:
    return WetlabDBCompoundRepository(catalog)


def _require_collection_editor(
    request: Request,
    user: User,
    database: str,
    collection: str,
) -> None:
    authz: AuthorizationService = request.app.state.authorization
    if not authz.can_edit(user, database, collection):
        raise HTTPException(status_code=403, detail="Edit access required for this collection")


@router.get("/projects")
def search_projects(
    q: str = "",
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    _: User = Depends(get_current_user),
    repo: WetlabDBCompoundRepository = Depends(get_sar_repo),
):
    page = repo.search_projects(q, cursor, limit)
    return {
        "projects": [{"id": p.id, "name": p.name} for p in page.items],
        "next_cursor": page.next_cursor,
    }


@router.get("/projects/{project_id}/series")
def list_series(
    project_id: str,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    _: User = Depends(get_current_user),
    repo: WetlabDBCompoundRepository = Depends(get_sar_repo),
):
    try:
        page = repo.list_series(project_id, cursor, limit)
    except SarRepositoryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "series": [
            {"id": s.id, "project_id": s.project_id, "name": s.name}
            for s in page.items
        ],
        "next_cursor": page.next_cursor,
    }


@router.get("/projects/{project_id}/series/{series_id}")
def get_series_snapshot(
    project_id: str,
    series_id: str,
    assays: str = Query("", description="Comma-separated assay field ids"),
    ids: str = Query("", description="Comma-separated compound _id values"),
    _: User = Depends(get_current_user),
    repo: WetlabDBCompoundRepository = Depends(get_sar_repo),
):
    assay_ids = [a.strip() for a in assays.split(",") if a.strip()]
    compound_ids = [i.strip() for i in ids.split(",") if i.strip()] or None
    try:
        snapshot = repo.get_series_snapshot(
            project_id,
            series_id,
            assay_ids,
            compound_ids=compound_ids,
        )
    except SarRepositoryError as exc:
        msg = str(exc)
        status = 400 if "compounds" in msg.lower() or "maximum" in msg.lower() else 404
        raise HTTPException(status_code=status, detail=msg) from exc
    return snapshot.to_dict()


@router.get("/sar/limits")
def sar_limits(_: User = Depends(get_current_user)):
    """Published resource limits and status vocabulary IDs (Slice 7)."""
    return {
        "max_alignment_compounds": MAX_ALIGNMENT_COMPOUNDS,
        "live_align_max_compounds": LIVE_ALIGN_MAX_COMPOUNDS,
        "max_optimizer_time_seconds": MAX_OPTIMIZER_TIME_SECONDS,
        "alignment_run_timeout_seconds": ALIGNMENT_RUN_TIMEOUT_SECONDS,
        "benchmark_compound_counts": list(BENCHMARK_COMPOUND_COUNTS),
        "status_case_messages": STATUS_CASE_MESSAGES,
    }


@router.get("/sar/assay-fields")
def list_assay_fields(_: User = Depends(get_current_user)):
    fields = []
    for field_id in list_assay_field_ids():
        spec = COMPOUND_FORM[field_id]
        fields.append(
            {
                "id": field_id,
                "name": field_id,
                "type": spec["type"],
                "default_unit": parse_unit_from_field_name(field_id),
            }
        )
    return {"assay_fields": fields}


class CorePreviewMolecule(BaseModel):
    id: str
    smiles: str


class CorePreviewBody(BaseModel):
    reference_smiles: str
    core_atoms: list[int] = Field(default_factory=list)
    molecules: list[CorePreviewMolecule] = Field(default_factory=list)
    ignore_bond_order: bool = False
    atom_modes: dict[str, str] = Field(default_factory=dict)
    remap_smarts: str = ""


class DepictBody(BaseModel):
    smiles: str
    width: int = Field(280, ge=80, le=800)
    height: int = Field(200, ge=80, le=800)
    highlight: list[int] = Field(default_factory=list)
    selected: list[int] = Field(default_factory=list)
    fragment_atoms: list[int] = Field(default_factory=list)
    molblock: str = ""
    core_atom_modes: dict[str, str] = Field(default_factory=dict)
    query_labels: bool = False


class CoreAnalogGeneralizeBody(BaseModel):
    reference_smiles: str
    core_atoms: list[int] = Field(default_factory=list)
    atom_modes: dict[str, str] = Field(default_factory=dict)
    analog_smiles: str
    analog_atom_index: int
    ignore_bond_order: bool = False


@router.post("/sar/core-analog-generalize")
def sar_core_analog_generalize(body: CoreAnalogGeneralizeBody, _: User = Depends(get_current_user)):
    from wetlabdb.api.metrics import record_operation
    from wetlabdb.sar.pipeline.core_pick import generalize_core_from_analog

    record_operation("sar.core_analog_generalize")

    modes: dict[int, str] | None = None
    if body.atom_modes:
        modes = {}
        for key, value in body.atom_modes.items():
            try:
                modes[int(key)] = str(value)
            except (TypeError, ValueError):
                continue
    return generalize_core_from_analog(
        body.reference_smiles,
        body.core_atoms,
        modes,
        body.analog_smiles,
        body.analog_atom_index,
        ignore_bond_order=body.ignore_bond_order,
    )


@router.post("/sar/core-preview")
def sar_core_preview(body: CorePreviewBody, _: User = Depends(get_current_user)):
    from wetlabdb.api.metrics import record_operation
    from wetlabdb.sar.pipeline.core_pick import preview_core

    record_operation("sar.core_preview")

    modes: dict[int, str] | None = None
    if body.atom_modes:
        modes = {}
        for key, value in body.atom_modes.items():
            try:
                modes[int(key)] = str(value)
            except (TypeError, ValueError):
                continue
    return preview_core(
        body.reference_smiles,
        body.core_atoms,
        [{"id": m.id, "smiles": m.smiles} for m in body.molecules],
        ignore_bond_order=body.ignore_bond_order,
        atom_modes=modes,
        remap_smarts=body.remap_smarts or None,
    )


class GuessCoreBody(BaseModel):
    reference_id: str | None = None
    molecules: list[CorePreviewMolecule] = Field(default_factory=list)
    ignore_bond_order: bool = False


@router.post("/sar/guess-core")
def sar_guess_core(body: GuessCoreBody, _: User = Depends(get_current_user)):
    from wetlabdb.api.metrics import record_operation
    from wetlabdb.sar.pipeline.core_pick import guess_shared_core

    record_operation("sar.guess_core")

    return guess_shared_core(
        [{"id": m.id, "smiles": m.smiles} for m in body.molecules],
        reference_id=body.reference_id,
        ignore_bond_order=body.ignore_bond_order,
    )


@router.post("/sar/depict")
def sar_depict(body: DepictBody, _: User = Depends(get_current_user)):
    from wetlabdb.api.metrics import record_operation
    from wetlabdb.sar.pipeline.core_pick import depict_structure

    record_operation("sar.depict")
    modes = None
    if body.core_atom_modes:
        modes = {int(key): str(value) for key, value in body.core_atom_modes.items()}
    drawn = depict_structure(
        body.smiles,
        width=body.width,
        height=body.height,
        highlight=body.highlight,
        selected=body.selected,
        fragment_atoms=body.fragment_atoms,
        molblock=body.molblock or None,
        core_atom_modes=modes,
        query_labels=body.query_labels,
    )
    if drawn is None:
        raise HTTPException(status_code=422, detail="Could not depict structure")
    return drawn


class RotatePoseMolecule(BaseModel):
    id: str
    smiles: str = ""
    molblock: str = ""


class RotatePosesBody(BaseModel):
    degrees: float
    molecules: list[RotatePoseMolecule] = Field(default_factory=list)


@router.post("/sar/rotate-poses")
def sar_rotate_poses(body: RotatePosesBody, _: User = Depends(get_current_user)):
    from wetlabdb.api.metrics import record_operation
    from wetlabdb.sar.pipeline.core_pick import rotate_poses

    record_operation("sar.rotate_poses")

    return {
        "poses": rotate_poses(
            [{"id": m.id, "smiles": m.smiles, "molblock": m.molblock} for m in body.molecules],
            body.degrees,
        )
    }


class AlignmentPoseBody(BaseModel):
    id: str
    molblock: str = ""


class AlignmentRunBody(BaseModel):
    project_id: str
    series_id: str
    database: str = "WetlabDB"
    collection: str = "Compounds"
    compound_ids: list[str] = Field(min_length=1)
    assay_ids: list[str] = Field(default_factory=list)
    reference_id: str
    mode: str = "same_scaffold"
    core_smarts: str = "c1ccccc1"
    ignore_bond_order: bool = False
    scaffold_element_mode: str = "from_smarts"
    poses: list[AlignmentPoseBody] = Field(default_factory=list)


@router.post("/alignment/run")
def run_alignment(
    body: AlignmentRunBody,
    request: Request,
    user: User = Depends(get_current_user),
    repo: WetlabDBCompoundRepository = Depends(get_sar_repo),
):
    """Fixed-core, ring-atom, or scaffold alignment for a selected snapshot."""
    from wetlabdb.api.metrics import record_operation

    _require_collection_editor(request, user, body.database, body.collection)
    record_operation("sar.alignment.run")
    try:
        snapshot = repo.get_series_snapshot(
            body.project_id,
            body.series_id,
            body.assay_ids,
            compound_ids=body.compound_ids,
        )
    except SarRepositoryError as exc:
        msg = str(exc)
        status = 400 if "compounds" in msg.lower() or "maximum" in msg.lower() else 404
        raise HTTPException(status_code=status, detail=msg) from exc

    snap_dict = snapshot.to_dict()
    try:
        result = run_from_snapshot(
            snap_dict,
            reference_id=body.reference_id,
            mode=body.mode,
            core_smarts=body.core_smarts,
            ignore_bond_order=body.ignore_bond_order,
            scaffold_element_mode=body.scaffold_element_mode,
            poses={p.id: p.molblock for p in body.poses if str(p.molblock or "").strip()},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return result_to_response(result, snap_dict)


def _alignment_progress_events(
    snap_dict: dict,
    body: AlignmentRunBody,
):
    events: queue.Queue[dict | None] = queue.Queue()

    def progress(phase: str, done: int = 0, total: int = 0) -> None:
        events.put({"phase": phase, "done": int(done), "total": int(total)})

    def worker() -> None:
        try:
            result = run_from_snapshot(
                snap_dict,
                reference_id=body.reference_id,
                mode=body.mode,
                core_smarts=body.core_smarts,
                ignore_bond_order=body.ignore_bond_order,
                scaffold_element_mode=body.scaffold_element_mode,
                poses={p.id: p.molblock for p in body.poses if str(p.molblock or "").strip()},
                progress=progress,
            )
            events.put({"phase": "done", "result": result_to_response(result, snap_dict)})
        except ValueError as exc:
            events.put({"phase": "error", "detail": str(exc)})
        except Exception as exc:
            events.put({"phase": "error", "detail": str(exc)})
        finally:
            events.put(None)

    threading.Thread(target=worker, daemon=True).start()
    yield json.dumps({"phase": "ingest", "done": 0, "total": len(body.compound_ids)}) + "\n"
    while True:
        item = events.get()
        if item is None:
            break
        yield json.dumps(item) + "\n"


@router.post("/alignment/run-progress")
def run_alignment_progress(
    body: AlignmentRunBody,
    request: Request,
    user: User = Depends(get_current_user),
    repo: WetlabDBCompoundRepository = Depends(get_sar_repo),
):
    """Same as ``/alignment/run``, but streams NDJSON progress then the result."""
    from wetlabdb.api.metrics import record_operation

    _require_collection_editor(request, user, body.database, body.collection)
    record_operation("sar.alignment.run_progress")
    try:
        snapshot = repo.get_series_snapshot(
            body.project_id,
            body.series_id,
            body.assay_ids,
            compound_ids=body.compound_ids,
        )
    except SarRepositoryError as exc:
        msg = str(exc)
        status = 400 if "compounds" in msg.lower() or "maximum" in msg.lower() else 404
        raise HTTPException(status_code=status, detail=msg) from exc

    return StreamingResponse(
        _alignment_progress_events(snapshot.to_dict(), body),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def get_sar_sidecar(request: Request) -> SarAlignmentSidecar:
    return request.app.state.sar_sidecar


class CreateAlignmentProjectBody(BaseModel):
    project_id: str
    series_id: str
    database: str = "WetlabDB"
    collection: str = "Compounds"
    compound_ids: list[str] = Field(min_length=1)
    assay_ids: list[str] = Field(default_factory=list)
    reference_id: str
    mode: str = "same_scaffold"
    core_smarts: str = "c1ccccc1"
    snapshot_revision: str
    draft_solution: dict


class PatchAlignmentProjectBody(BaseModel):
    expected_version: int = Field(ge=1)
    draft_solution: dict
    snapshot_revision: str | None = None
    force_unapproved_edit: bool = False
    database: str = "WetlabDB"
    collection: str = "Compounds"


class ApproveAlignmentProjectBody(BaseModel):
    expected_version: int = Field(ge=1)
    snapshot_revision: str
    database: str = "WetlabDB"
    collection: str = "Compounds"


def _project_payload(project: AlignmentProject) -> dict:
    return {
        "id": project.id,
        "version": project.version,
        "owner": project.owner,
        "project_id": project.project_id,
        "series_id": project.series_id,
        "compound_ids": project.compound_ids,
        "assay_ids": project.assay_ids,
        "reference_id": project.reference_id,
        "mode": project.mode,
        "core_smarts": project.core_smarts,
        "snapshot_revision": project.snapshot_revision,
        "draft_solution": project.draft_solution,
        "approval": project.approval,
        "audit": project.audit,
    }


def _project_summary(project: AlignmentProject) -> dict:
    return {
        "id": project.id,
        "version": project.version,
        "owner": project.owner,
        "project_id": project.project_id,
        "series_id": project.series_id,
        "compound_count": len(project.compound_ids),
        "mode": project.mode,
        "core_smarts": project.core_smarts,
        "approved": project.approval is not None,
        "updated_at": last_audit_at(project),
        "reference_id": project.reference_id,
    }


@router.get("/alignment-projects")
def list_alignment_projects(
    project_id: str | None = None,
    series_id: str | None = None,
    limit: int = Query(12, ge=1, le=50),
    _: User = Depends(get_current_user),
    sidecar: SarAlignmentSidecar = Depends(get_sar_sidecar),
):
    items = sidecar.list_projects(
        project_id=project_id,
        series_id=series_id,
        limit=limit,
    )
    return {"projects": [_project_summary(p) for p in items]}


@router.post("/alignment-projects")
def create_alignment_project(
    body: CreateAlignmentProjectBody,
    request: Request,
    user: User = Depends(get_current_user),
    sidecar: SarAlignmentSidecar = Depends(get_sar_sidecar),
):
    from wetlabdb.api.metrics import record_operation

    _require_collection_editor(request, user, body.database, body.collection)
    record_operation("sar.alignment.project.create")
    project = sidecar.create_project(
        owner=user.username,
        project_id=body.project_id,
        series_id=body.series_id,
        compound_ids=body.compound_ids,
        assay_ids=body.assay_ids,
        reference_id=body.reference_id,
        mode=body.mode,
        core_smarts=body.core_smarts,
        snapshot_revision=body.snapshot_revision,
        draft_solution=body.draft_solution,
    )
    return _project_payload(project)


@router.get("/alignment-projects/{project_id}")
def get_alignment_project(
    project_id: str,
    _: User = Depends(get_current_user),
    sidecar: SarAlignmentSidecar = Depends(get_sar_sidecar),
):
    try:
        project = sidecar.get_project(project_id)
    except SidecarNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _project_payload(project)


@router.patch("/alignment-projects/{project_id}")
def patch_alignment_project(
    project_id: str,
    body: PatchAlignmentProjectBody,
    request: Request,
    user: User = Depends(get_current_user),
    sidecar: SarAlignmentSidecar = Depends(get_sar_sidecar),
):
    _require_collection_editor(request, user, body.database, body.collection)
    try:
        project = sidecar.patch_draft(
            project_id,
            expected_version=body.expected_version,
            actor=user.username,
            draft_solution=body.draft_solution,
            snapshot_revision=body.snapshot_revision,
            force_unapproved_edit=body.force_unapproved_edit,
        )
    except SidecarNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SidecarConcurrencyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _project_payload(project)


@router.post("/alignment-projects/{project_id}/approve")
def approve_alignment_project(
    project_id: str,
    body: ApproveAlignmentProjectBody,
    request: Request,
    user: User = Depends(get_current_user),
    sidecar: SarAlignmentSidecar = Depends(get_sar_sidecar),
):
    _require_collection_editor(request, user, body.database, body.collection)
    try:
        project = sidecar.approve(
            project_id,
            expected_version=body.expected_version,
            actor=user.username,
            snapshot_revision=body.snapshot_revision,
        )
    except SidecarNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SidecarConcurrencyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _project_payload(project)
