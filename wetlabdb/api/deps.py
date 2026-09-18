"""FastAPI dependencies: current user, admin gate, catalog/compound services."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from wetlabdb.services.auth import User
from wetlabdb.services.catalog import CatalogError, CatalogService
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


def collection_or_404(
    database: str,
    collection: str,
    catalog: CatalogService = Depends(get_catalog),
):
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
    database: str,
    collection: str,
    coll=Depends(collection_or_404),
) -> SearchService:
    return SearchService(coll)


__all__ = [
    "collection_or_404",
    "compounds_for",
    "get_catalog",
    "get_current_user",
    "require_admin",
    "search_for",
]
