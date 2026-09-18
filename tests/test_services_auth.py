"""Tests for :class:`wetlabdb.services.AuthService`."""

from __future__ import annotations

import pytest

from wetlabdb.services.auth import AuthError, AuthService


@pytest.fixture
def auth(tmp_path):
    return AuthService.json_store(str(tmp_path))


def test_bootstrap_creates_first_admin_only(auth):
    created = auth.bootstrap("admin", "secret")
    assert created is not None and created.admin is True
    assert auth.verify("admin", "secret") is not None
    assert auth.bootstrap("admin", "other") is None
    assert auth.verify("admin", "other") is None
    assert auth.verify("admin", "secret") is not None


def test_create_and_verify_non_admin(auth):
    auth.bootstrap("admin", "secret")
    user = auth.create_user("lab", "pw", admin=False)
    assert user.admin is False
    assert auth.verify("lab", "pw") is not None
    assert auth.verify("lab", "nope") is None


def test_duplicate_user_raises(auth):
    auth.create_user("a", "pw")
    with pytest.raises(AuthError):
        auth.create_user("a", "pw")


def test_update_password(auth):
    auth.create_user("a", "old")
    auth.update_user("a", password="new")
    assert auth.verify("a", "old") is None
    assert auth.verify("a", "new") is not None
