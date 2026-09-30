"""Database / collection catalog routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from wetlabdb.api.audit_log import record_audit
from wetlabdb.api.deps import get_authorization, get_catalog, get_current_user, require_admin, require_permissions_staff
from wetlabdb.services.auth import User
from wetlabdb.services.catalog import CatalogError, CatalogService
from wetlabdb.services.authorization import AuthorizationService, default_policy
from wetlabdb.services.catalog_names import CATALOG_NAME_MAX_LEN, InvalidCatalogNameError, validate_catalog_name

router = APIRouter()


class CreateDatabaseBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=CATALOG_NAME_MAX_LEN)
    collection: str = Field(default="Compounds", min_length=1, max_length=CATALOG_NAME_MAX_LEN)


class CreateCollectionBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=CATALOG_NAME_MAX_LEN)


@router.get("/databases")
def list_databases(
    authz=Depends(get_authorization),
    user: User = Depends(get_current_user),
):
    return {"databases": authz.list_accessible_databases(user)}


@router.post("/databases", status_code=201)
def create_database(
    body: CreateDatabaseBody,
    request: Request,
    catalog: CatalogService = Depends(get_catalog),
    _: User = Depends(require_admin),
):
    try:
        catalog.create_database(body.name, body.collection)
    except CatalogError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_audit(
        request,
        action="catalog.database.create",
        target=f"database:{body.name}",
        summary={"collection": body.collection},
    )
    return {"name": body.name, "collection": body.collection}


@router.delete("/databases/{database}")
def drop_database(
    database: str,
    request: Request,
    catalog: CatalogService = Depends(get_catalog),
    _: User = Depends(require_admin),
):
    try:
        validate_catalog_name(database, kind="database")
    except InvalidCatalogNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        catalog.drop_database(database)
    except CatalogError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_audit(request, action="catalog.database.drop", target=f"database:{database}")
    return {"ok": True}


@router.get("/databases/{database}/collections")
def list_collections(
    database: str,
    authz=Depends(get_authorization),
    user: User = Depends(get_current_user),
):
    try:
        validate_catalog_name(database, kind="database")
    except InvalidCatalogNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not authz.list_accessible_databases(user) or database not in authz.list_accessible_databases(user):
        if not user.admin:
            raise HTTPException(status_code=403, detail="No access to this database")
    try:
        names = authz.list_accessible_collections(user, database)
    except CatalogError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"collections": names}


@router.post("/databases/{database}/collections", status_code=201)
def create_collection(
    database: str,
    body: CreateCollectionBody,
    request: Request,
    catalog: CatalogService = Depends(get_catalog),
    authz: AuthorizationService = Depends(get_authorization),
    user: User = Depends(require_permissions_staff),
):
    if not user.admin and database not in authz.list_accessible_databases(user):
        raise HTTPException(status_code=403, detail="No access to this database")
    try:
        catalog.create_collection(database, body.name)
    except CatalogError as exc:
        status = 404 if "not available" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    authz.ensure_default_policy(
        database,
        body.name,
    )
    if not user.admin:
        authz.set_policy(
            user,
            default_policy(database, body.name, owner=user.username),
        )
    record_audit(
        request,
        action="catalog.collection.create",
        target=f"{database}/{body.name}",
    )
    return {"name": body.name}


@router.delete("/databases/{database}/collections/{collection}")
def drop_collection(
    database: str,
    collection: str,
    request: Request,
    catalog: CatalogService = Depends(get_catalog),
    _: User = Depends(require_admin),
):
    try:
        validate_catalog_name(database, kind="database")
        validate_catalog_name(collection, kind="collection")
    except InvalidCatalogNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        catalog.drop_collection(database, collection)
    except CatalogError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    record_audit(
        request,
        action="catalog.collection.drop",
        target=f"{database}/{collection}",
    )
    return {"ok": True}
