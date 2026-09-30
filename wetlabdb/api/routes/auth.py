"""Auth and user-management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from wetlabdb.api.audit_log import record_audit
from wetlabdb.api.deps import get_current_user, require_admin
from wetlabdb.services.auth import AuthError, User

router = APIRouter()


class LoginBody(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=256)


class CreateUserBody(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=256)
    admin: bool = False
    kind: str = "student"


class PatchUserBody(BaseModel):
    password: str | None = Field(default=None, max_length=256)
    admin: bool | None = None
    kind: str | None = None


@router.post("/login")
def login(request: Request, body: LoginBody):
    limiter = request.app.state.login_rate_limiter
    client_host = request.client.host if request.client else "unknown"
    if limiter.is_blocked(client_host, body.username):
        raise HTTPException(status_code=429, detail="Too many login attempts; try again later")
    user = request.app.state.auth.verify(body.username, body.password)
    if user is None:
        limiter.record_failure(client_host, body.username)
        record_audit(
            request,
            action="login.failure",
            target=f"user:{body.username}",
            actor=body.username,
            summary={"client": client_host},
        )
        raise HTTPException(status_code=401, detail="Invalid username or password")
    limiter.reset(client_host, body.username)
    request.session["username"] = user.username
    record_audit(request, action="login.success", target=f"user:{user.username}")
    return user.public_dict()


@router.post("/logout")
def logout(request: Request):
    record_audit(request, action="logout", target="session")
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user.public_dict()


@router.get("/users")
def list_users(request: Request, _: User = Depends(require_admin)):
    return [u.public_dict() for u in request.app.state.auth.list_users()]


@router.post("/users", status_code=201)
def create_user(
    request: Request,
    body: CreateUserBody,
    _: User = Depends(require_admin),
):
    try:
        user = request.app.state.auth.create_user(
            body.username, body.password, admin=body.admin, kind=body.kind
        )
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_audit(
        request,
        action="user.create",
        target=f"user:{user.username}",
        summary={"admin": user.admin},
    )
    return user.public_dict()


@router.patch("/users/{username}")
def patch_user(
    request: Request,
    username: str,
    body: PatchUserBody,
    current: User = Depends(get_current_user),
):
    if username != current.username and not current.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    if body.admin is not None and not current.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    if body.kind is not None and not current.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    if body.password is None and body.admin is None and body.kind is None:
        raise HTTPException(status_code=400, detail="Nothing to update")
    try:
        user = request.app.state.auth.update_user(
            username,
            password=body.password,
            admin=body.admin,
            kind=body.kind,
        )
    except AuthError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    summary: dict = {}
    if body.password is not None:
        summary["password_changed"] = True
    if body.admin is not None:
        summary["admin"] = body.admin
    record_audit(request, action="user.update", target=f"user:{user.username}", summary=summary)
    return user.public_dict()


@router.delete("/users/{username}")
def delete_user_route(
    request: Request,
    username: str,
    current: User = Depends(require_admin),
):
    target = username.strip()
    if target == current.username:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    auth = request.app.state.auth
    user = auth.get(target)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User '{target}' not found")
    if user.admin:
        admins = [u for u in auth.list_users() if u.admin]
        if len(admins) <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the only admin account")
    try:
        auth.delete_user(target)
    except AuthError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    record_audit(request, action="user.delete", target=f"user:{target}")
    return {"ok": True}
