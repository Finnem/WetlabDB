"""Logic-only tests for the admin-writes gate on :class:`MongoBrowser`.

The gate decides whether the create/delete database & collection buttons
should be enabled. We don't want to instantiate Tk widgets in unit tests,
so we call the unbound method against a tiny stand-in object exposing
just ``self.config``. That keeps the test fast, headless, and tied
exactly to the rule we care about (mode == 'local' OR admin_access).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.fixture
def admin_gate():
    """Return the unbound ``_admin_writes_allowed`` so we can call it on a stub.

    Imported lazily because :mod:`wetlabdb.ui.app` pulls in tkinter, PIL,
    pandas and rdkit at import time -- still pure Python (no display
    needed), but heavy enough to skip when not required.
    """
    from wetlabdb.ui.app import MongoBrowser

    return MongoBrowser._admin_writes_allowed


def _stub(**config_overrides):
    return SimpleNamespace(config=dict(config_overrides))


def test_local_mode_always_allows_admin(admin_gate):
    assert admin_gate(_stub(mode="local")) is True
    # Even with admin_access explicitly disabled, local mode still wins.
    assert admin_gate(_stub(mode="local", admin_access=False)) is True


def test_remote_mode_blocks_when_admin_access_off(admin_gate):
    assert admin_gate(_stub(mode="remote")) is False
    assert admin_gate(_stub(mode="remote", admin_access=False)) is False


def test_remote_mode_allows_when_admin_access_on(admin_gate):
    assert admin_gate(_stub(mode="remote", admin_access=True)) is True


def test_missing_mode_treated_as_remote_by_default(admin_gate):
    """Defensive: an empty / missing mode key must NOT silently grant admin.

    Bug guard against a regression where ``mode`` defaults to local.
    """
    assert admin_gate(_stub()) is False
    assert admin_gate(_stub(admin_access=False)) is False
    assert admin_gate(_stub(admin_access=True)) is True


def test_mode_is_case_insensitive(admin_gate):
    assert admin_gate(_stub(mode="LOCAL")) is True
    assert admin_gate(_stub(mode="Local")) is True
    assert admin_gate(_stub(mode="REMOTE", admin_access=True)) is True


def test_admin_access_truthy_values_enable_remote(admin_gate):
    """Persisted JSON may store admin_access as 1 / 'true' / etc."""
    assert admin_gate(_stub(mode="remote", admin_access=1)) is True
    assert admin_gate(_stub(mode="remote", admin_access="yes")) is True
    # And explicitly falsy values stay blocked.
    assert admin_gate(_stub(mode="remote", admin_access=0)) is False
    assert admin_gate(_stub(mode="remote", admin_access="")) is False
