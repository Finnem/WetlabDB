"""Collection access policy API (admin and employees)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from wetlabdb.api.audit_log import record_audit
from wetlabdb.api.deps import (
    get_authorization,
    get_current_user,
    require_permissions_staff,
)
from wetlabdb.services.auth import User
from wetlabdb.services.authorization import AuthorizationError, AuthorizationService, CollectionAccessPolicy

router = APIRouter()


class CollectionPolicyBody(BaseModel):
    owner: str | None = None
    visibility: str = "employees_and_students"
    custom_users: list[str] = Field(default_factory=list)
    student_access: str = "viewer"
    employee_access: str = "editor"


@router.get("/access/collection-policies")
def list_collection_policies(
    authz: AuthorizationService = Depends(get_authorization),
    staff: User = Depends(require_permissions_staff),
):
    policies = authz.list_policies_for_ui(staff)
    return {"policies": [p.to_dict() for p in policies]}


@router.get("/databases/{database}/collections/{collection}/access-policy")
def get_collection_policy(
    database: str,
    collection: str,
    authz: AuthorizationService = Depends(get_authorization),
    staff: User = Depends(require_permissions_staff),
):
    if not authz.can_manage_policy(staff, database, collection) and not staff.admin:
        if not authz.can_view(staff, database, collection):
            raise HTTPException(status_code=403, detail="Not allowed to view this policy")
    policy = authz.policy_for(database, collection)
    return policy.to_dict()


@router.put("/databases/{database}/collections/{collection}/access-policy")
def put_collection_policy(
    database: str,
    collection: str,
    body: CollectionPolicyBody,
    request: Request,
    authz: AuthorizationService = Depends(get_authorization),
    staff: User = Depends(require_permissions_staff),
):
    policy = CollectionAccessPolicy(
        database=database,
        collection=collection,
        owner=body.owner,
        visibility=body.visibility,  # type: ignore[arg-type]
        custom_users=body.custom_users,
        student_access=body.student_access,  # type: ignore[arg-type]
        employee_access=body.employee_access,  # type: ignore[arg-type]
    )
    try:
        saved = authz.set_policy(staff, policy)
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    record_audit(
        request,
        action="access.policy.update",
        target=f"{database}/{collection}",
        summary={"visibility": saved.visibility, "owner": saved.owner},
    )
    return saved.to_dict()
