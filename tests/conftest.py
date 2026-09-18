"""Shared pytest fixtures for the wetlabdb test-suite."""

from __future__ import annotations

import pytest


@pytest.fixture
def local_client(tmp_path):
    """Return a fresh :class:`wetlabdb.storage.LocalClient` rooted in ``tmp_path``.

    The bootstrap default ``WetlabDB/Compounds`` is suppressed so individual
    tests can decide their own seed data.
    """
    from wetlabdb.storage import get_local_client

    return get_local_client(str(tmp_path), bootstrap_db=None)


@pytest.fixture
def bootstrapped_client(tmp_path):
    """Like :func:`local_client` but with the default WetlabDB/Compounds bootstrap."""
    from wetlabdb.storage import get_local_client

    return get_local_client(str(tmp_path))


@pytest.fixture
def sample_compounds():
    """Three well-known small molecules used across multiple test modules."""
    return [
        {"Name": "Aspirin", "SMILES": "CC(=O)OC1=CC=CC=C1C(=O)O", "CAS Nr": "50-78-2"},
        {"Name": "Caffeine", "SMILES": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C", "CAS Nr": "58-08-2"},
        {"Name": "Toluene", "SMILES": "Cc1ccccc1", "CAS Nr": "108-88-3"},
    ]
