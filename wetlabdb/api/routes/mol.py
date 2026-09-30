"""MOL export (aligned 2D structures)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.responses import Response

from wetlabdb.api.deps import compounds_for, get_current_user
from wetlabdb.chem.align import (
    MolExportError,
    PageMolItem,
    compounds_to_mol_zip,
    compounds_to_sdf,
    compounds_to_page_cdxml,
    compounds_to_page_mol,
    page_items_to_mol_zip,
    page_items_to_sdf,
    rows_from_docs,
)
from wetlabdb.services.auth import User
from wetlabdb.services.authorization import AuthorizationService
from wetlabdb.services.compounds import CompoundService

router = APIRouter()


def _require_collection_viewer(
    request: Request,
    user: User,
    database: str,
    collection: str,
) -> None:
    authz: AuthorizationService = request.app.state.authorization
    if not authz.can_view(user, database, collection):
        raise HTTPException(status_code=403, detail="No access to this collection")


class MolExportBody(BaseModel):
    ids: list[str] = Field(..., min_length=1)
    format: str = "zip"


@router.post("/databases/{database}/collections/{collection}/mol/export")
def mol_export(
    body: MolExportBody,
    svc: CompoundService = Depends(compounds_for),
    _: User = Depends(get_current_user),
):
    from wetlabdb.api.metrics import record_operation

    record_operation("mol.export")
    docs: list[dict] = []
    for doc_id in body.ids:
        doc = svc.get(doc_id)
        if doc is not None:
            docs.append(doc)
    if not docs:
        raise HTTPException(status_code=404, detail="No matching compounds")
    rows = rows_from_docs(docs)
    fmt = (body.format or "zip").lower()
    try:
        if fmt == "sdf":
            payload, filename = compounds_to_sdf(rows)
        elif fmt in ("zip", "mol"):
            zip_payload, filename = compounds_to_mol_zip(rows)
        else:
            raise HTTPException(status_code=422, detail=f"Unsupported format: {body.format}")
    except MolExportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if fmt == "sdf":
        return Response(
            content=payload.encode("utf-8"),
            media_type="chemical/x-mdl-sdfile",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return Response(
        content=zip_payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class MolPageItemBody(BaseModel):
    id: str = ""
    name: str = ""
    smiles: str = ""
    molblock: str = ""


class MolPageBody(BaseModel):
    database: str = "WetlabDB"
    collection: str = "Compounds"
    molecules: list[MolPageItemBody] = Field(..., min_length=1)
    columns: int | None = Field(default=None, ge=1, le=40)
    filename: str = "figure.mol"
    format: str = "mol"


@router.post("/mol/page")
def mol_page(
    body: MolPageBody,
    request: Request,
    user: User = Depends(get_current_user),
):
    from wetlabdb.api.metrics import record_operation

    record_operation("mol.page")
    _require_collection_viewer(request, user, body.database, body.collection)
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


class MolBulkBody(BaseModel):
    database: str = "WetlabDB"
    collection: str = "Compounds"
    molecules: list[MolPageItemBody] = Field(..., min_length=1)
    format: str = "zip"
    filename: str = "compounds.zip"


@router.post("/mol/bulk")
def mol_bulk(
    body: MolBulkBody,
    request: Request,
    user: User = Depends(get_current_user),
):
    from wetlabdb.api.metrics import record_operation

    record_operation("mol.bulk")
    _require_collection_viewer(request, user, body.database, body.collection)
    items = [
        PageMolItem(
            doc_id=row.id,
            name=row.name,
            smiles=row.smiles,
            molblock=row.molblock,
        )
        for row in body.molecules
    ]
    fmt = (body.format or "zip").lower()
    try:
        if fmt == "sdf":
            payload, out_name = page_items_to_sdf(items, filename=body.filename)
            return Response(
                content=payload.encode("utf-8"),
                media_type="chemical/x-mdl-sdfile",
                headers={"Content-Disposition": f'attachment; filename="{out_name}"'},
            )
        if fmt in ("zip", "mol"):
            archive = body.filename if body.filename.lower().endswith(".zip") else "compounds.zip"
            zip_payload, out_name = page_items_to_mol_zip(items, archive_name=archive)
            return Response(
                content=zip_payload,
                media_type="application/zip",
                headers={"Content-Disposition": f'attachment; filename="{out_name}"'},
            )
    except MolExportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=f"Unsupported format: {body.format}")
