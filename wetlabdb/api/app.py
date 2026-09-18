"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from wetlabdb.api.routes import auth as auth_routes
from wetlabdb.api.routes import catalog as catalog_routes
from wetlabdb.api.routes import compounds as compound_routes
from wetlabdb.api.routes import csv as csv_routes
from wetlabdb.api.routes import mol as mol_routes
from wetlabdb.api.routes import meta as meta_routes
from wetlabdb.api.routes import search as search_routes
from wetlabdb.services.auth import AuthService
from wetlabdb.settings import Settings
from wetlabdb.storage.base import StorageClientProto
from wetlabdb.storage.local import get_local_client


def _build_client(settings: Settings) -> StorageClientProto:
    if settings.is_local:
        return get_local_client(settings.data_dir)
    from wetlabdb.storage.mongo import get_mongo_client

    return get_mongo_client(settings.mongo_uri)


def _build_auth(settings: Settings, client: StorageClientProto) -> AuthService:
    if settings.is_local:
        return AuthService.json_store(settings.data_dir)
    return AuthService.mongo_store(client)


def create_app(
    *,
    settings: Settings | None = None,
    client: StorageClientProto | None = None,
    auth: AuthService | None = None,
    mount_spa: bool = True,
) -> FastAPI:
    """Build the WetlabDB web application.

    Tests inject ``settings`` / ``client`` / ``auth``. Production uses
    :meth:`Settings.from_env`.
    """
    settings = settings or Settings.from_env()
    client = client or _build_client(settings)
    auth = auth or _build_auth(settings, client)
    if settings.admin_user and settings.admin_password:
        auth.bootstrap(settings.admin_user, settings.admin_password)

    app = FastAPI(title="WetlabDB", version="0.3.0")
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        same_site="lax",
        https_only=False,
    )
    app.state.settings = settings
    app.state.client = client
    app.state.auth = auth

    prefix = "/api"
    app.include_router(meta_routes.router, prefix=prefix)
    app.include_router(auth_routes.router, prefix=prefix)
    app.include_router(catalog_routes.router, prefix=prefix)
    app.include_router(compound_routes.router, prefix=prefix)
    app.include_router(search_routes.router, prefix=prefix)
    app.include_router(csv_routes.router, prefix=prefix)
    app.include_router(mol_routes.router, prefix=prefix)

    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if mount_spa and dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="spa")

    return app


def get_app() -> FastAPI:
    """ASGI entry point used by uvicorn: ``wetlabdb.api.app:get_app``."""
    return create_app()


__all__ = ["create_app", "get_app"]
