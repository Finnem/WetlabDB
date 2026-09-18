"""Auth and user-management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from wetlabdb.api.deps import get_current_user, require_admin
from wetlabdb.services.auth import AuthError, User

router = APIRouter()


class LoginBody(BaseModel):
    username: str
    password: str


class CreateUserBody(BaseModel):
    username: str
    password: str
    admin: bool = False


class PatchUserBody(BaseModel):
    password: str | None = None
    admin: bool | None = None


@router.post("/login")
def login(request: Request, body: LoginBody):
    user = request.app.state.auth.verify(body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    request.session["username"] = user.username
    return user.public_dict()


@router.post("/logout")
def logout(request: Request):
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
            body.username, body.password, admin=body.admin
        )
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return user.public_dict()


@router.patch("/users/{username}")
def patch_user(
    request: Request,
    username: str,
    body: PatchUserBody,
    current: User = Depends(get_current_user),
):
    if body.admin is not None and not current.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    if username != current.username and not current.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    if body.password is None and body.admin is None:
        raise HTTPException(status_code=400, detail="Nothing to update")
    try:
        user = request.app.state.auth.update_user(
            username, password=body.password, admin=body.admin
        )
    except AuthError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return user.public_dict()
