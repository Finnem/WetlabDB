"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, cast

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from wetlabdb.api.access_log import AccessLogMiddleware
from wetlabdb.api.http_security import LimitBodySizeMiddleware, MutationHeaderMiddleware
from wetlabdb.api.lifecycle import app_lifespan
from wetlabdb.api.rate_limit import login_rate_limiter
from wetlabdb.api.request_id import RequestIdMiddleware
from wetlabdb.api.routes import access as access_routes
from wetlabdb.api.routes import audit as audit_routes
from wetlabdb.api.routes import auth as auth_routes
from wetlabdb.api.routes import catalog as catalog_routes
from wetlabdb.api.routes import compounds as compound_routes
from wetlabdb.api.routes import csv as csv_routes
from wetlabdb.api.routes import mol as mol_routes
from wetlabdb.api.routes import meta as meta_routes
from wetlabdb.api.routes import sar as sar_routes
from wetlabdb.api.routes import search as search_routes
from wetlabdb.services.auth import AuthService
from wetlabdb.services.audit import AuditService, audit_store_for
from wetlabdb.services.authorization import AuthorizationService, default_policy, policy_store_for
from wetlabdb.services.compound_revisions import CompoundRevisionService, revision_store_for
from wetlabdb.services.catalog import CatalogService
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


def _seed_default_policies(authz: AuthorizationService, client: StorageClientProto) -> None:
    """Ensure default lab collection policies exist for bootstrap data."""
    try:
        catalog = CatalogService(client)
        for database in catalog.list_databases():
            for collection in catalog.list_collections(database):
                authz.ensure_default_policy(database, collection)
    except Exception:
        return


def create_app(
    *,
    settings: Settings | None = None,
    client: StorageClientProto | None = None,
    auth: AuthService | None = None,
    mount_spa: bool = True,
    require_mutation_header: bool = True,
) -> FastAPI:
    """Build the WetlabDB web application.

    Tests inject ``settings`` / ``client`` / ``auth``. Production uses
    :meth:`Settings.from_env`.
    """
    settings = settings or Settings.from_env()
    settings.validate_for_runtime()
    client = client or _build_client(settings)
    auth = auth or _build_auth(settings, client)
    from wetlabdb.storage.mongo_indexes import ensure_deployment_indexes

    ensure_deployment_indexes(settings, client)
    if settings.admin_user and settings.admin_password:
        auth.bootstrap(settings.admin_user, settings.admin_password)

    app = FastAPI(title="WetlabDB", version="0.3.0", lifespan=app_lifespan)
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(
        MutationHeaderMiddleware,
        enabled=require_mutation_header,
    )
    app.add_middleware(LimitBodySizeMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie="wetlabdb_session",
        max_age=settings.session_max_age,
        same_site=cast(Literal["lax", "strict", "none"], settings.session_same_site),
        https_only=settings.session_https_only,
    )
    app.state.settings = settings
    app.state.client = client
    app.state.auth = auth
    app.state.login_rate_limiter = login_rate_limiter
    app.state.audit = AuditService(audit_store_for(settings, client))
    app.state.compound_revisions = CompoundRevisionService(
        revision_store_for(settings, client)
    )
    catalog = CatalogService(client)
    app.state.catalog = catalog
    app.state.authorization = AuthorizationService(
        policy_store_for(is_local=settings.is_local, data_dir=settings.data_dir, client=client),
        catalog,
    )
    _seed_default_policies(app.state.authorization, client)

    from wetlabdb.sar.sidecar import SarAlignmentSidecar

    app.state.sar_sidecar = SarAlignmentSidecar.from_settings(
        is_local=settings.is_local,
        data_dir=settings.data_dir,
        client=client,
    )

    prefix = "/api"
    app.include_router(meta_routes.router, prefix=prefix)
    app.include_router(auth_routes.router, prefix=prefix)
    app.include_router(audit_routes.router, prefix=prefix)
    app.include_router(access_routes.router, prefix=prefix)
    app.include_router(catalog_routes.router, prefix=prefix)
    app.include_router(compound_routes.router, prefix=prefix)
    app.include_router(search_routes.router, prefix=prefix)
    app.include_router(csv_routes.router, prefix=prefix)
    app.include_router(mol_routes.router, prefix=prefix)
    app.include_router(sar_routes.router, prefix=prefix)

    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if mount_spa and dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="spa")

    return app


def get_app() -> FastAPI:
    """ASGI entry point used by uvicorn: ``wetlabdb.api.app:get_app``."""
    return create_app()


__all__ = ["create_app", "get_app"]
