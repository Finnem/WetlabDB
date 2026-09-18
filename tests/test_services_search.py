"""Tests for :class:`wetlabdb.services.SearchService`."""

from __future__ import annotations

import pytest

from wetlabdb.services import CompoundService, SearchService
from wetlabdb.storage import LocalCollection


@pytest.fixture
def search(tmp_path, sample_compounds):
    coll = LocalCollection(str(tmp_path / "x.json"))
    svc = CompoundService(coll)
    for doc in sample_compounds:
        svc.add(doc)
    return SearchService(coll)


def test_similarity_smiles_input_returns_self_at_top(search):
    hits = search.similarity("CC(=O)OC1=CC=CC=C1C(=O)O", cutoff=0.5)
    assert hits and hits[0].document["Name"] == "Aspirin"
    assert hits[0].similarity == pytest.approx(1.0)


def test_similarity_bracket_atom_smiles_is_not_treated_as_smarts(tmp_path):
    smiles = "C1CCCC2CCC[SH]2CCC1"
    coll = LocalCollection(str(tmp_path / "x.json"))
    svc = CompoundService(coll)
    svc.add({"Name": "bracketed sulfur", "SMILES": smiles})

    hits = SearchService(coll).similarity(smiles, cutoff=0.99)

    assert hits and hits[0].document["Name"] == "bracketed sulfur"
    assert hits[0].similarity == pytest.approx(1.0)


def test_similarity_smarts_input_enumerates_queries(search):
    hits = search.similarity("[#6][#6]", cutoff=0.0)
    assert hits  # at least something should match


def test_similarity_empty_query_returns_empty(search):
    assert search.similarity("") == []


def test_similarity_invalid_query_returns_empty(search):
    assert search.similarity("zzz??!!", cutoff=0.0) == []


def test_substructure_benzene_matches_aromatic_compounds(search):
    hits = search.substructure("c1ccccc1")
    names = sorted(h.document["Name"] for h in hits)
    # Aspirin, Caffeine, and Toluene all contain a benzene-like ring; Caffeine
    # has a 5+6 fused aromatic system but no 6-membered benzene per se, so
    # we only assert on the obvious matches.
    assert "Aspirin" in names
    assert "Toluene" in names


def test_substructure_empty_query_returns_empty(search):
    assert search.substructure("") == []


def test_substructure_invalid_query_returns_empty(search):
    assert search.substructure("nonsense [[[") == []
