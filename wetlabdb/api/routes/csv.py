"""CSV import / table export."""

from __future__ import annotations

import io

import pandas as pd
from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response

from wetlabdb.api.deps import collection_or_404, compounds_for, get_current_user
from wetlabdb.api.serialize import doc_row
from wetlabdb.schema.compound import DEFAULT_VISIBLE_COLUMNS
from wetlabdb.services.auth import User
from wetlabdb.services.compounds import CompoundService
from wetlabdb.services.csv_io import export_csv_text, import_csv

router = APIRouter()


@router.post("/databases/{database}/collections/{collection}/csv/import")
def csv_import(
    file: UploadFile,
    identifier_col: str = Form(...),
    data_cols: str = Form(...),
    coll=Depends(collection_or_404),
    _: User = Depends(get_current_user),
):
    """Import a CSV. ``data_cols`` is a comma-separated list of column names."""
    raw = file.file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid CSV: {exc}") from exc
    columns = [c.strip() for c in data_cols.split(",") if c.strip()]
    if identifier_col not in df.columns:
        raise HTTPException(
            status_code=400, detail=f"Identifier column {identifier_col!r} not in CSV"
        )
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise HTTPException(
            status_code=400, detail=f"Missing CSV columns: {missing}"
        )
    summary = import_csv(coll, df, identifier_col, columns)
    return {
        "created": summary.created,
        "updated": summary.updated,
        "total": summary.total,
    }


@router.get("/databases/{database}/collections/{collection}/csv/export")
def csv_export(
    columns: str | None = Query(None),
    q: str | None = None,
    column: str | None = None,
    svc: CompoundService = Depends(compounds_for),
    _: User = Depends(get_current_user),
):
    headers = (
        [c.strip() for c in columns.split(",") if c.strip()]
        if columns
        else list(DEFAULT_VISIBLE_COLUMNS)
    )
    docs = svc.list_filtered(q=q, column=column)
    rows = [doc_row(doc, headers) for doc in docs]
    text = export_csv_text(rows, headers)
    return Response(
        content=text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="compounds_export.csv"'
        },
    )
