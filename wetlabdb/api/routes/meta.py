"""Schema / health routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from wetlabdb.api.deps import get_current_user
from wetlabdb.chem import molfile_to_storage_string, smiles_to_3d_molblock
from wetlabdb.schema.compound import (
    COMPOUND_FORM,
    CSV_IDENTIFIER_COLUMNS,
    DEFAULT_VISIBLE_COLUMNS,
    default_compound_document,
)
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
    return {"ok": True}
