"""Tests for :mod:`wetlabdb.chem.similarity`."""

from __future__ import annotations

import pytest

from wetlabdb.chem.similarity import (
    METRIC_DEFAULT_CUTOFFS,
    METRIC_DESCRIPTIONS,
    SIMILARITY_METRICS,
    compute_similarity,
    similarity_search,
    tanimoto_similarity,
)
from wetlabdb.chem.smiles import parse_smiles


def test_identical_molecules_have_similarity_one():
    a = parse_smiles("CCO")
    assert tanimoto_similarity(a, a) == 1.0


def test_distant_molecules_low_similarity():
    a = parse_smiles("C")
    b = parse_smiles("c1ccc2c(c1)ccc1ccc3ccccc3c12")  # large polyaromatic
    assert tanimoto_similarity(a, b) < 0.3


def test_none_inputs_score_zero():
    assert tanimoto_similarity(None, parse_smiles("CCO")) == 0.0
    assert tanimoto_similarity(parse_smiles("CCO"), None) == 0.0
    assert tanimoto_similarity(None, None) == 0.0


def test_similarity_search_filters_by_cutoff_and_orders_by_score():
    docs = [
        {"_id": "1", "Name": "ethanol", "SMILES": "CCO"},
        {"_id": "2", "Name": "methanol", "SMILES": "CO"},
        {"_id": "3", "Name": "propanol", "SMILES": "CCCO"},
        {"_id": "4", "Name": "benzene", "SMILES": "c1ccccc1"},
        {"_id": "5", "Name": "nada", "SMILES": ""},  # filtered out
    ]
    query = parse_smiles("CCO")
    hits = similarity_search(docs, [query], cutoff=0.3)

    names = [h.document["Name"] for h in hits]
    # Top hit must be the exact match.
    assert names[0] == "ethanol"
    assert hits[0].similarity == 1.0
    # Sorted descending.
    scores = [h.similarity for h in hits]
    assert scores == sorted(scores, reverse=True)
    # Cutoff is honoured.
    assert all(h.similarity >= 0.3 for h in hits)


def test_similarity_search_uses_max_over_query_set():
    docs = [{"_id": "x", "SMILES": "CCO"}]
    benzene = parse_smiles("c1ccccc1")
    ethanol = parse_smiles("CCO")
    hits = similarity_search(docs, [benzene, ethanol], cutoff=0.0)
    assert len(hits) == 1
    assert hits[0].similarity == 1.0


def test_similarity_search_skips_unparsable_smiles():
    docs = [
        {"_id": "1", "SMILES": "not-real-???"},
        {"_id": "2", "SMILES": "CCO"},
    ]
    hits = similarity_search(docs, [parse_smiles("CCO")], cutoff=0.0)
    assert len(hits) == 1
    assert hits[0].document["_id"] == "2"


@pytest.mark.parametrize("metric", list(SIMILARITY_METRICS.keys()))
def test_compute_similarity_self_match_is_max_for_every_metric(metric):
    """Every supported metric should report a self-match as a top-tier score.

    Most coefficients return 1.0 for identical fingerprints; McConnaughey can
    technically exceed 1.0 numerically with binary inputs, but it is always
    >= every cross-pair score, so we just sanity-check that.
    """
    mol = parse_smiles("CCOc1ccccc1")
    self_score = compute_similarity(mol, mol, metric=metric)
    other = parse_smiles("c1ccccc1")
    cross = compute_similarity(mol, other, metric=metric)
    assert self_score >= cross


def test_compute_similarity_unknown_metric_falls_back_to_tanimoto():
    a = parse_smiles("CCO")
    b = parse_smiles("CCN")
    fallback = compute_similarity(a, b, metric="DefinitelyNotARealMetric")
    expected = compute_similarity(a, b, metric="Tanimoto")
    assert fallback == expected


def test_similarity_search_dice_disagrees_with_tanimoto_but_orders_consistently():
    """Sanity-check that switching metric changes the absolute scores while
    keeping the ranking intact for a small, well-behaved set of analogues."""
    docs = [
        {"_id": "1", "Name": "ethanol", "SMILES": "CCO"},
        {"_id": "2", "Name": "methanol", "SMILES": "CO"},
        {"_id": "3", "Name": "propanol", "SMILES": "CCCO"},
    ]
    query = parse_smiles("CCO")
    tani = similarity_search(docs, [query], cutoff=0.0, metric="Tanimoto")
    dice = similarity_search(docs, [query], cutoff=0.0, metric="Dice")

    # Both metrics agree on the top hit (the exact match).
    assert tani[0].document["Name"] == dice[0].document["Name"] == "ethanol"
    # And both produce a 1.0 self-similarity for the exact match.
    assert tani[0].similarity == 1.0
    assert dice[0].similarity == 1.0
    # But mid-list scores genuinely differ between the two metrics.
    assert tani[1].similarity != dice[1].similarity


def test_tanimoto_wrapper_matches_compute_similarity():
    a = parse_smiles("CCO")
    b = parse_smiles("c1ccccc1")
    assert tanimoto_similarity(a, b) == compute_similarity(a, b, metric="Tanimoto")


def test_every_metric_has_default_cutoff_and_description():
    """Adding a metric without a cutoff/description silently degrades the UI
    (no per-metric default, no tooltip text), so guard against that here."""
    missing_cutoffs = set(SIMILARITY_METRICS) - set(METRIC_DEFAULT_CUTOFFS)
    missing_descriptions = set(SIMILARITY_METRICS) - set(METRIC_DESCRIPTIONS)
    assert not missing_cutoffs, f"missing default cutoffs: {missing_cutoffs}"
    assert not missing_descriptions, (
        f"missing descriptions: {missing_descriptions}"
    )
