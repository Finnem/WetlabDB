"""Compound CRUD and PNG rendering."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from wetlabdb.api.audit_log import record_audit
from wetlabdb.api.deps import compounds_for, get_current_user, require_admin, require_collection_editor
from wetlabdb.api.serialize import serialize_doc, serialize_docs
from wetlabdb.services.compound_list import DEFAULT_COMPOUND_PAGE_SIZE, MAX_COMPOUND_PAGE_SIZE
from wetlabdb.services.compound_fields import InvalidFieldSelectionError, parse_field_selection
from wetlabdb.chem import render_to_png_bytes
from wetlabdb.services.auth import User
from wetlabdb.services.compound_meta import DELETED_AT, DELETED_BY
from wetlabdb.services.compound_revisions import CompoundRevisionService
from wetlabdb.services.compounds import CompoundService

router = APIRouter()


class CompoundBody(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
    unset: list[str] = Field(default_factory=list)


def _revisions(request: Request) -> CompoundRevisionService:
    return request.app.state.compound_revisions


def _serialize_trash(doc: dict) -> dict:
    payload = serialize_doc(doc) or {}
    payload["deleted_at"] = doc.get(DELETED_AT)
    payload["deleted_by"] = doc.get(DELETED_BY)
    return payload


@router.get("/databases/{database}/collections/{collection}/compounds")
def list_compounds(
    q: str | None = None,
    column: str | None = None,
    limit: int | None = Query(None, ge=1, le=MAX_COMPOUND_PAGE_SIZE),
    cursor: str | None = Query(None),
    fields: str | None = Query(None, description="Comma-separated field names to return"),
    svc: CompoundService = Depends(compounds_for),
    _: User = Depends(get_current_user),
):
    try:
        selected = parse_field_selection(fields)
    except InvalidFieldSelectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    filtered = svc.list_paginated(
        q=q, column=column, limit=limit, cursor=cursor, fields=selected
    )
    body: dict = {
        "compounds": serialize_docs(filtered.compounds),
        "total": filtered.total,
    }
    if limit is not None or cursor:
        body["next_cursor"] = filtered.next_cursor
        body["limit"] = limit or DEFAULT_COMPOUND_PAGE_SIZE
    return body


@router.get("/databases/{database}/collections/{collection}/compounds/deleted")
def list_deleted_compounds(
    svc: CompoundService = Depends(compounds_for),
    _: User = Depends(require_admin),
):
    return {"compounds": [_serialize_trash(d) for d in svc.list_deleted()]}


@router.post(
    "/databases/{database}/collections/{collection}/compounds",
    status_code=201,
)
def add_compound(
    database: str,
    collection: str,
    body: CompoundBody,
    request: Request,
    svc: CompoundService = Depends(compounds_for),
    _: User = Depends(require_collection_editor),
):
    inserted_id = svc.add(body.data)
    doc = svc.get(inserted_id)
    record_audit(
        request,
        action="compound.create",
        target=f"{database}/{collection}/{inserted_id}",
    )
    return serialize_doc(doc)


@router.get("/databases/{database}/collections/{collection}/compounds/{doc_id}")
def get_compound(
    doc_id: str,
    svc: CompoundService = Depends(compounds_for),
    _: User = Depends(get_current_user),
):
    doc = svc.get(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Compound not found")
    return serialize_doc(doc)


@router.get("/databases/{database}/collections/{collection}/compounds/{doc_id}/revisions")
def list_compound_revisions(
    database: str,
    collection: str,
    doc_id: str,
    svc: CompoundService = Depends(compounds_for),
    revisions: CompoundRevisionService = Depends(_revisions),
    _: User = Depends(require_collection_editor),
):
    if svc.get(doc_id, include_deleted=True) is None:
        raise HTTPException(status_code=404, detail="Compound not found")
    return {
        "revisions": revisions.list_for(database, collection, doc_id),
    }


@router.put("/databases/{database}/collections/{collection}/compounds/{doc_id}")
def update_compound(
    database: str,
    collection: str,
    doc_id: str,
    body: CompoundBody,
    request: Request,
    user: User = Depends(require_collection_editor),
    svc: CompoundService = Depends(compounds_for),
    revisions: CompoundRevisionService = Depends(_revisions),
):
    current = svc.get(doc_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Compound not found")
    revisions.record_snapshot(
        database=database,
        collection=collection,
        doc_id=str(doc_id),
        actor=user.username,
        document=current,
    )
    data = dict(body.data)
    data.pop("_id", None)
    svc.update(doc_id, data, unset=body.unset)
    record_audit(
        request,
        action="compound.update",
        target=f"{database}/{collection}/{doc_id}",
        summary={"unset": body.unset},
    )
    return serialize_doc(svc.get(doc_id))


@router.post("/databases/{database}/collections/{collection}/compounds/{doc_id}/restore")
def restore_compound(
    database: str,
    collection: str,
    doc_id: str,
    request: Request,
    svc: CompoundService = Depends(compounds_for),
    _: User = Depends(require_collection_editor),
):
    if not svc.restore(doc_id):
        raise HTTPException(status_code=404, detail="Compound not in trash")
    record_audit(
        request,
        action="compound.restore",
        target=f"{database}/{collection}/{doc_id}",
    )
    return serialize_doc(svc.get(doc_id))


@router.delete("/databases/{database}/collections/{collection}/compounds/{doc_id}")
def delete_compound(
    database: str,
    collection: str,
    doc_id: str,
    request: Request,
    hard: bool = Query(False),
    user: User = Depends(require_collection_editor),
    svc: CompoundService = Depends(compounds_for),
):
    if hard:
        if not user.admin:
            raise HTTPException(status_code=403, detail="Permanent delete requires admin")
        if not svc.hard_delete(doc_id):
            raise HTTPException(status_code=404, detail="Compound not found")
        record_audit(
            request,
            action="compound.hard_delete",
            target=f"{database}/{collection}/{doc_id}",
        )
        return {"ok": True, "permanent": True}

    if not svc.soft_delete(doc_id, actor=user.username):
        raise HTTPException(status_code=404, detail="Compound not found")
    record_audit(
        request,
        action="compound.soft_delete",
        target=f"{database}/{collection}/{doc_id}",
    )
    return {"ok": True, "permanent": False}


@router.get("/render.png")
def render_png(
    smiles: str = Query(...),
    w: int = Query(300, ge=16, le=2000),
    h: int = Query(300, ge=16, le=2000),
    highlight: str | None = None,
    _: User = Depends(get_current_user),
):
    from wetlabdb.api.metrics import record_operation

    record_operation("chem.render_png")
    highlight_atoms = None
    if highlight:
        try:
            highlight_atoms = [
                int(part) for part in highlight.split(",") if part.strip()
            ]
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail="highlight must be comma-separated integers"
            ) from exc
    png = render_to_png_bytes(
        smiles,
        width=w,
        height=h,
        highlight_atoms=highlight_atoms,
        background=(1.0, 1.0, 1.0, 1.0),
    )
    if png is None:
        raise HTTPException(status_code=404, detail="Could not render structure")
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )
