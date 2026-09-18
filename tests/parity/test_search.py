"""Parity: molecular search matching MolecularSearchWindow."""

from __future__ import annotations

import pytest

from wetlabdb.chem.similarity import (
    DEFAULT_METRIC,
    METRIC_DEFAULT_CUTOFFS,
    SIMILARITY_METRICS,
)


def _similarity(client, **body):
    return client.post(
        "/api/databases/WetlabDB/collections/Compounds/search/similarity",
        json=body,
    )


def _substructure(client, query):
    return client.post(
        "/api/databases/WetlabDB/collections/Compounds/search/substructure",
        json={"query": query},
    )


def test_metrics_catalog(admin_client):
    body = admin_client.get("/api/search/metrics").json()
    assert body["default"] == DEFAULT_METRIC
    assert body["metrics"] == list(SIMILARITY_METRICS.keys())
    assert body["cutoffs"] == METRIC_DEFAULT_CUTOFFS
    for name in SIMILARITY_METRICS:
        assert name in body["cutoffs"]


def test_similarity_aspirin_at_cutoff(admin_client):
    response = _similarity(
        admin_client,
        query="CC(=O)OC1=CC=CC=C1C(=O)O",
        cutoff=0.5,
        metric="Tanimoto",
    )
    assert response.status_code == 200
    hits = response.json()["hits"]
    assert hits
    assert hits[0]["document"]["Name"] == "Aspirin"
    assert hits[0]["similarity"] == pytest.approx(1.0)


def test_similarity_sort_all_returns_every_comparable(admin_client):
    filtered = _similarity(
        admin_client,
        query="CC(=O)OC1=CC=CC=C1C(=O)O",
        cutoff=0.99,
        metric="Tanimoto",
        sort_all=False,
    ).json()["hits"]
    sorted_all = _similarity(
        admin_client,
        query="CC(=O)OC1=CC=CC=C1C(=O)O",
        cutoff=0.99,
        metric="Tanimoto",
        sort_all=True,
    ).json()["hits"]
    assert len(sorted_all) >= len(filtered)
    scores = [h["similarity"] for h in sorted_all]
    assert scores == sorted(scores, reverse=True)
    names = {h["document"]["Name"] for h in sorted_all}
    assert "Aspirin" in names
    assert "Toluene" in names


def test_unknown_metric_falls_back_to_tanimoto(admin_client):
    tanimoto = _similarity(
        admin_client,
        query="CC(=O)OC1=CC=CC=C1C(=O)O",
        cutoff=0.0,
        metric="Tanimoto",
    ).json()["hits"]
    fallback = _similarity(
        admin_client,
        query="CC(=O)OC1=CC=CC=C1C(=O)O",
        cutoff=0.0,
        metric="NotARealMetric",
    ).json()["hits"]
    assert [h["similarity"] for h in tanimoto] == [h["similarity"] for h in fallback]


def test_every_named_metric_is_accepted(admin_client):
    for metric in SIMILARITY_METRICS:
        response = _similarity(
            admin_client,
            query="CCO",
            cutoff=-1.0,
            metric=metric,
        )
        assert response.status_code == 200, metric


def test_empty_and_invalid_similarity_return_empty(admin_client):
    assert _similarity(admin_client, query="").json()["hits"] == []
    assert _similarity(admin_client, query="zzz??!!", cutoff=0.0).json()["hits"] == []


def test_substructure_benzene(admin_client):
    hits = _substructure(admin_client, "c1ccccc1").json()["hits"]
    names = {h["document"]["Name"] for h in hits}
    assert "Aspirin" in names
    assert "Toluene" in names


def test_substructure_empty_and_invalid(admin_client):
    assert _substructure(admin_client, "").json()["hits"] == []
    assert _substructure(admin_client, "nonsense [[[").json()["hits"] == []


def test_kekule_smarts_from_editor_matches_aromatic(admin_client):
    query = "[#6]1=[#6]-[#6]=[#6]-[#6]=[#6]-1"
    hits = _substructure(admin_client, query).json()["hits"]
    names = {h["document"]["Name"] for h in hits}
    assert "Toluene" in names
    assert "Aspirin" in names
