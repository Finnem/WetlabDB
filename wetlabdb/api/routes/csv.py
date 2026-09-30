"""CSV import / table export."""

from __future__ import annotations

import io

import pandas as pd
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response

from wetlabdb.api.audit_log import record_audit
from wetlabdb.api.deps import collection_or_404, compounds_for, get_current_user, require_collection_editor
from wetlabdb.api.serialize import doc_row
from wetlabdb.schema.compound import DEFAULT_VISIBLE_COLUMNS
from wetlabdb.services.auth import User
from wetlabdb.services.compounds import CompoundService
from wetlabdb.services.csv_io import (
    CsvShapeError,
    MAX_CSV_UPLOAD_BYTES,
    ensure_csv_shape,
    export_csv_text,
    import_csv,
    preview_csv,
)

router = APIRouter()


def _parse_csv_import(
    file: UploadFile,
    identifier_col: str,
    data_cols: str,
    on_collision: str,
):
    allowed_types = {
        "text/csv",
        "application/csv",
        "application/vnd.ms-excel",
        "application/octet-stream",
        "",
    }
    if file.content_type and file.content_type not in allowed_types:
        raise HTTPException(status_code=415, detail="Unsupported file type; upload CSV")

    raw = file.file.read(MAX_CSV_UPLOAD_BYTES + 1)
    if len(raw) > MAX_CSV_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="CSV upload too large")
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid CSV: {exc}") from exc
    try:
        ensure_csv_shape(df)
    except CsvShapeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
    mode = on_collision.strip().lower()
    if mode not in ("append", "overwrite"):
        raise HTTPException(
            status_code=400, detail="on_collision must be 'append' or 'overwrite'"
        )
    return df, columns, mode


@router.post("/databases/{database}/collections/{collection}/csv/preview")
def csv_import_preview(
    database: str,
    collection: str,
    file: UploadFile,
    identifier_col: str = Form(...),
    data_cols: str = Form(...),
    on_collision: str = Form("append"),
    coll=Depends(collection_or_404),
    _: User = Depends(require_collection_editor),
):
    """Dry-run CSV import; returns the same counts as import without writing."""
    df, columns, mode = _parse_csv_import(file, identifier_col, data_cols, on_collision)
    summary = preview_csv(coll, df, identifier_col, columns, on_collision=mode)
    return {
        "created": summary.created,
        "updated": summary.updated,
        "appended": summary.appended,
        "total": summary.total,
        "on_collision": mode,
        "dry_run": True,
    }


@router.post("/databases/{database}/collections/{collection}/csv/import")
def csv_import(
    database: str,
    collection: str,
    request: Request,
    file: UploadFile,
    identifier_col: str = Form(...),
    data_cols: str = Form(...),
    on_collision: str = Form("append"),
    coll=Depends(collection_or_404),
    _: User = Depends(require_collection_editor),
):
    """Import a CSV. ``data_cols`` is a comma-separated list of column names.

    ``on_collision`` is ``append`` (default) or ``overwrite``.
    """
    df, columns, mode = _parse_csv_import(file, identifier_col, data_cols, on_collision)
    summary = import_csv(coll, df, identifier_col, columns, on_collision=mode)
    from wetlabdb.api.metrics import record_operation

    record_operation("csv.import")
    record_audit(
        request,
        action="csv.import",
        target=f"{database}/{collection}",
        summary={
            "created": summary.created,
            "updated": summary.updated,
            "appended": summary.appended,
            "on_collision": mode,
        },
    )
    return {
        "created": summary.created,
        "updated": summary.updated,
        "appended": summary.appended,
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
