"""Schema / health / metrics routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from wetlabdb.api.deps import get_current_user, require_admin
from wetlabdb.api.metrics import prometheus_text, snapshot
from wetlabdb.api.readiness import check_readiness
from wetlabdb.api.http_security import MAX_BODY_BYTES
from wetlabdb.chem import molfile_to_storage_string, smiles_to_3d_molblock
from wetlabdb.services.csv_io import MAX_CSV_COLUMNS, MAX_CSV_ROWS, MAX_CSV_UPLOAD_BYTES
from wetlabdb.schema.compound import (
    COMPOUND_FORM,
    CSV_IDENTIFIER_COLUMNS,
    DEFAULT_VISIBLE_COLUMNS,
    default_compound_document,
)
from wetlabdb.services.compound_list import MAX_COMPOUND_PAGE_SIZE
from wetlabdb.services.auth import User

router = APIRouter()


class MolfileBody(BaseModel):
    molfile: str


@router.get("/schema/compound")
def compound_schema(_: User = Depends(get_current_user)):
    return {
        "fields": COMPOUND_FORM,
        "defaults": default_compound_document(),
        "visible_columns": DEFAULT_VISIBLE_COLUMNS,
        "csv_identifiers": CSV_IDENTIFIER_COLUMNS,
    }


@router.post("/chem/from-molfile")
def from_molfile(body: MolfileBody, _: User = Depends(get_current_user)):
    text = molfile_to_storage_string(body.molfile)
    if not text:
        raise HTTPException(status_code=422, detail="Could not parse molfile")
    return {"smiles": text}


@router.get("/chem/3d.mol")
def chem_3d_mol(
    smiles: str = Query(...),
    _: User = Depends(get_current_user),
):
    molblock = smiles_to_3d_molblock(smiles)
    if molblock is None:
        raise HTTPException(status_code=404, detail="Could not build 3D structure")
    return PlainTextResponse(
        content=molblock,
        media_type="chemical/x-mdl-molfile",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/health")
def health():
    """Liveness: process is up (no dependency checks)."""
    return {"ok": True, "live": True}


@router.get("/health/live")
def health_live():
    return {"ok": True}


@router.get("/health/ready")
def health_ready(request: Request):
    settings = request.app.state.settings
    client = request.app.state.client
    return check_readiness(settings, client)


@router.get("/limits")
def operation_limits(request: Request, _: User = Depends(get_current_user)):
    """Documented synchronous bounds for imports, search, and HTTP bodies."""
    settings = request.app.state.settings
    return {
        "http_max_body_bytes": MAX_BODY_BYTES,
        "csv_max_upload_bytes": MAX_CSV_UPLOAD_BYTES,
        "csv_max_rows": MAX_CSV_ROWS,
        "csv_max_columns": MAX_CSV_COLUMNS,
        "search_max_compounds": settings.search_max_compounds,
        "chem_wall_timeout_sec": settings.chem_wall_timeout_sec,
        "compound_page_max": MAX_COMPOUND_PAGE_SIZE,
    }


@router.get("/metrics")
def metrics(_: User = Depends(require_admin)):
    return snapshot()


@router.get("/metrics/prometheus")
def metrics_prometheus(_: User = Depends(require_admin)):
    return PlainTextResponse(
        content=prometheus_text(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
