"""Database / collection catalog routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from wetlabdb.api.deps import get_catalog, get_current_user, require_admin
from wetlabdb.services.auth import User
from wetlabdb.services.catalog import CatalogError, CatalogService

router = APIRouter()


class CreateDatabaseBody(BaseModel):
    name: str
    collection: str = "Compounds"


class CreateCollectionBody(BaseModel):
    name: str


@router.get("/databases")
def list_databases(
    catalog: CatalogService = Depends(get_catalog),
    _: User = Depends(get_current_user),
):
    return {"databases": catalog.list_databases()}


@router.post("/databases", status_code=201)
def create_database(
    body: CreateDatabaseBody,
    catalog: CatalogService = Depends(get_catalog),
    _: User = Depends(require_admin),
):
    try:
        catalog.create_database(body.name, body.collection)
    except CatalogError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"name": body.name, "collection": body.collection}


@router.delete("/databases/{database}")
def drop_database(
    database: str,
    catalog: CatalogService = Depends(get_catalog),
    _: User = Depends(require_admin),
):
    try:
        catalog.drop_database(database)
    except CatalogError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/databases/{database}/collections")
def list_collections(
    database: str,
    catalog: CatalogService = Depends(get_catalog),
    _: User = Depends(get_current_user),
):
    try:
        names = catalog.list_collections(database)
    except CatalogError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"collections": names}


@router.post("/databases/{database}/collections", status_code=201)
def create_collection(
    database: str,
    body: CreateCollectionBody,
    catalog: CatalogService = Depends(get_catalog),
    _: User = Depends(require_admin),
):
    try:
        catalog.create_collection(database, body.name)
    except CatalogError as exc:
        status = 404 if "not available" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return {"name": body.name}


@router.delete("/databases/{database}/collections/{collection}")
def drop_collection(
    database: str,
    collection: str,
    catalog: CatalogService = Depends(get_catalog),
    _: User = Depends(require_admin),
):
    try:
        catalog.drop_collection(database, collection)
    except CatalogError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}
