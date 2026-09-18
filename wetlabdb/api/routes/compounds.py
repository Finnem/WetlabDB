"""Compound CRUD and PNG rendering."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from wetlabdb.api.deps import compounds_for, get_current_user
from wetlabdb.api.serialize import serialize_doc, serialize_docs
from wetlabdb.chem import render_to_png_bytes
from wetlabdb.services.auth import User
from wetlabdb.services.compounds import CompoundService

router = APIRouter()


class CompoundBody(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
    unset: list[str] = Field(default_factory=list)


@router.get("/databases/{database}/collections/{collection}/compounds")
def list_compounds(
    q: str | None = None,
    column: str | None = None,
    svc: CompoundService = Depends(compounds_for),
    _: User = Depends(get_current_user),
):
    docs = svc.list_filtered(q=q, column=column)
    return {"compounds": serialize_docs(docs)}


@router.post(
    "/databases/{database}/collections/{collection}/compounds",
    status_code=201,
)
def add_compound(
    body: CompoundBody,
    svc: CompoundService = Depends(compounds_for),
    _: User = Depends(get_current_user),
):
    inserted_id = svc.add(body.data)
    doc = svc.get(inserted_id)
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


@router.put("/databases/{database}/collections/{collection}/compounds/{doc_id}")
def update_compound(
    doc_id: str,
    body: CompoundBody,
    svc: CompoundService = Depends(compounds_for),
    _: User = Depends(get_current_user),
):
    if svc.get(doc_id) is None:
        raise HTTPException(status_code=404, detail="Compound not found")
    data = dict(body.data)
    data.pop("_id", None)
    svc.update(doc_id, data, unset=body.unset)
    return serialize_doc(svc.get(doc_id))


@router.delete("/databases/{database}/collections/{collection}/compounds/{doc_id}")
def delete_compound(
    doc_id: str,
    svc: CompoundService = Depends(compounds_for),
    _: User = Depends(get_current_user),
):
    if not svc.delete(doc_id):
        raise HTTPException(status_code=404, detail="Compound not found")
    return {"ok": True}


@router.get("/render.png")
def render_png(
    smiles: str = Query(...),
    w: int = Query(300, ge=16, le=2000),
    h: int = Query(300, ge=16, le=2000),
    highlight: str | None = None,
    _: User = Depends(get_current_user),
):
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
