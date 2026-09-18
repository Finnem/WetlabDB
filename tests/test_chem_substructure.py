"""Tests for :mod:`wetlabdb.chem.substructure`."""

from __future__ import annotations

from wetlabdb.chem.substructure import parse_smarts, substructure_search


def test_parse_smarts_valid():
    assert parse_smarts("c1ccccc1") is not None


def test_parse_smarts_invalid_returns_none():
    assert parse_smarts("not-smarts-???") is None
    assert parse_smarts("") is None
    assert parse_smarts(None) is None


def test_benzene_substructure_matches_toluene_not_methane():
    docs = [
        {"_id": "tol", "SMILES": "Cc1ccccc1"},
        {"_id": "met", "SMILES": "C"},
        {"_id": "phe", "SMILES": "c1ccccc1"},
    ]
    hits = substructure_search(docs, "c1ccccc1")
    ids = sorted(h.document["_id"] for h in hits)
    assert ids == ["phe", "tol"]


def test_invalid_smarts_returns_empty_list_no_crash():
    docs = [{"_id": "x", "SMILES": "CCO"}]
    assert substructure_search(docs, "this is total garbage [[[") == []


def test_skips_documents_without_smiles_or_unparsable():
    docs = [
        {"_id": "1"},  # no SMILES
        {"_id": "2", "SMILES": ""},  # empty
        {"_id": "3", "SMILES": "??!!"},  # unparsable
        {"_id": "4", "SMILES": "Cc1ccccc1"},  # valid match
    ]
    hits = substructure_search(docs, "c1ccccc1")
    assert [h.document["_id"] for h in hits] == ["4"]


def test_kekule_smarts_query_from_editor_matches_aromatic_smiles():
    """End-to-end regression for the user-reported bug.

    The 2D editor used to emit ``[#6]1=[#6]-[#6]=[#6]-[#6]=[#6]-1-*`` for
    "benzene + substituent". Without aromaticity perception in the search
    layer, that query matches *zero* documents -- even though the docs are
    all stored as aromatic SMILES (``c1ccccc1`` etc.).
    """
    docs = [
        {"_id": "phenol", "SMILES": "c1ccc(O)cc1"},
        {"_id": "paracetamol", "SMILES": "CC(=O)Nc1ccc(O)cc1"},
        {"_id": "toluene", "SMILES": "Cc1ccccc1"},
        # Negative controls: must NOT match.
        {"_id": "cyclohexanol", "SMILES": "C1CCCCC1O"},
        {"_id": "ethanol", "SMILES": "CCO"},
        {"_id": "bare_benzene", "SMILES": "c1ccccc1"},  # no substituent
    ]
    hits = substructure_search(docs, "[#6]1=[#6]-[#6]=[#6]-[#6]=[#6]-1-*")
    ids = sorted(h.document["_id"] for h in hits)
    assert ids == ["paracetamol", "phenol", "toluene"]
