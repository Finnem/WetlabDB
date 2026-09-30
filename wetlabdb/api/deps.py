"""FastAPI dependencies: current user, admin gate, catalog/compound services."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from wetlabdb.services.auth import User
from wetlabdb.services.authorization import AuthorizationService
from wetlabdb.services.catalog import CatalogError, CatalogService
from wetlabdb.services.catalog_names import InvalidCatalogNameError, validate_catalog_name
from wetlabdb.services.compounds import CompoundService
from wetlabdb.services.search import SearchService


def get_catalog(request: Request) -> CatalogService:
    return CatalogService(request.app.state.client)


def get_current_user(request: Request) -> User:
    username = request.session.get("username")
    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = request.app.state.auth.get(username)
    if user is None:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def get_authorization(request: Request) -> AuthorizationService:
    return request.app.state.authorization


def require_permissions_staff(user: User = Depends(get_current_user)) -> User:
    if not AuthorizationService.can_open_permissions_ui(user):
        raise HTTPException(status_code=403, detail="Employee or admin access required")
    return user


def require_collection_viewer(
    database: str,
    collection: str,
    user: User = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authorization),
) -> User:
    try:
        validate_catalog_name(database, kind="database")
        validate_catalog_name(collection, kind="collection")
    except InvalidCatalogNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not authz.can_view(user, database, collection):
        raise HTTPException(status_code=403, detail="No access to this collection")
    return user


def require_collection_editor(
    database: str,
    collection: str,
    user: User = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authorization),
) -> User:
    try:
        validate_catalog_name(database, kind="database")
        validate_catalog_name(collection, kind="collection")
    except InvalidCatalogNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not authz.can_edit(user, database, collection):
        raise HTTPException(status_code=403, detail="Edit access required for this collection")
    return user


def collection_or_404(
    database: str,
    collection: str,
    catalog: CatalogService = Depends(get_catalog),
    _: User = Depends(require_collection_viewer),
):
    try:
        validate_catalog_name(database, kind="database")
        validate_catalog_name(collection, kind="collection")
    except InvalidCatalogNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        names = catalog.list_collections(database)
    except CatalogError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if collection not in names:
        raise HTTPException(status_code=404, detail="Collection not found")
    return catalog.collection(database, collection)


def compounds_for(
    database: str,
    collection: str,
    coll=Depends(collection_or_404),
) -> CompoundService:
    return CompoundService(coll)


def search_for(
    request: Request,
    database: str,
    collection: str,
    coll=Depends(collection_or_404),
) -> SearchService:
    settings = request.app.state.settings
    return SearchService(coll, max_compounds=settings.search_max_compounds)


__all__ = [
    "collection_or_404",
    "compounds_for",
    "get_authorization",
    "get_catalog",
    "get_current_user",
    "require_admin",
    "require_collection_editor",
    "require_collection_viewer",
    "require_permissions_staff",
    "search_for",
]
