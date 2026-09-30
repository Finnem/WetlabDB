"""MOL export (aligned 2D structures)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette.responses import Response

from wetlabdb.api.deps import compounds_for, get_current_user
from wetlabdb.chem.align import (
    MolExportError,
    PageMolItem,
    compounds_to_mol_zip,
    compounds_to_page_cdxml,
    compounds_to_page_mol,
    rows_from_docs,
)
from wetlabdb.services.auth import User
from wetlabdb.services.compounds import CompoundService

router = APIRouter()


class MolExportBody(BaseModel):
    ids: list[str] = Field(..., min_length=1)


@router.post("/databases/{database}/collections/{collection}/mol/export")
def mol_export(
    body: MolExportBody,
    svc: CompoundService = Depends(compounds_for),
    _: User = Depends(get_current_user),
):
    docs: list[dict] = []
    for doc_id in body.ids:
        doc = svc.get(doc_id)
        if doc is not None:
            docs.append(doc)
    if not docs:
        raise HTTPException(status_code=404, detail="No matching compounds")
    try:
        payload, filename = compounds_to_mol_zip(rows_from_docs(docs))
    except MolExportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class MolPageItemBody(BaseModel):
    id: str = ""
    name: str = ""
    smiles: str = ""
    molblock: str = ""


class MolPageBody(BaseModel):
    molecules: list[MolPageItemBody] = Field(..., min_length=1)
    columns: int | None = Field(default=None, ge=1, le=40)
    filename: str = "figure.mol"
    format: str = "mol"


@router.post("/mol/page")
def mol_page(
    body: MolPageBody,
    _: User = Depends(get_current_user),
):
    items = [
        PageMolItem(
            doc_id=row.id,
            name=row.name,
            smiles=row.smiles,
            molblock=row.molblock,
        )
        for row in body.molecules
    ]
    as_cdxml = body.format.lower() == "cdxml" or body.filename.lower().endswith(".cdxml")
    try:
        if as_cdxml:
            payload, filename = compounds_to_page_cdxml(
                items, columns=body.columns, filename=body.filename
            )
            media = "application/vnd.chemdraw+xml"
        else:
            payload, filename = compounds_to_page_mol(
                items, columns=body.columns, filename=body.filename
            )
            media = "chemical/x-mdl-molfile"
    except MolExportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=payload.encode("utf-8") if as_cdxml else payload,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
