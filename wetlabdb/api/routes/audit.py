"""Admin audit log read API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from wetlabdb.api.audit_serialize import serialize_audit_events
from wetlabdb.api.deps import require_admin
from wetlabdb.services.audit import AuditService
from wetlabdb.services.auth import User

router = APIRouter()


def get_audit_service(request: Request) -> AuditService:
    return request.app.state.audit


@router.get("/audit/events")
def list_audit_events(
    limit: int = Query(50, ge=1, le=500),
    _: User = Depends(require_admin),
    audit: AuditService = Depends(get_audit_service),
):
    return {"events": serialize_audit_events(audit.list_recent(limit=limit))}
