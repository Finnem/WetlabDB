"""Helpers to emit audit records from route handlers."""

from __future__ import annotations

from typing import Any

from starlette.requests import Request

from wetlabdb.services.audit import AuditService


def _audit_service(request: Request) -> AuditService | None:
    return getattr(request.app.state, "audit", None)


def record_audit(
    request: Request,
    *,
    action: str,
    target: str,
    summary: dict[str, Any] | None = None,
    actor: str | None = None,
) -> None:
    svc = _audit_service(request)
    if svc is None:
        return
    if actor is None:
        actor = request.session.get("username")
    request_id = getattr(request.state, "request_id", None)
    svc.record(
        action=action,
        target=target,
        actor=actor,
        summary=summary,
        request_id=request_id,
    )


__all__ = ["record_audit"]
