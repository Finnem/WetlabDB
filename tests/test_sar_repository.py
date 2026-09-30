"""Integration tests for :class:`WetlabDBCompoundRepository`."""

from __future__ import annotations

import pytest

from wetlabdb.services import CatalogService, CompoundService
from wetlabdb.sar import SarRepositoryError, WetlabDBCompoundRepository


@pytest.fixture
def sar_repo(local_client):
    catalog = CatalogService(local_client)
    catalog.create_database("SARTestProject", "Compounds")
    return WetlabDBCompoundRepository(catalog), catalog


def _seed_series(catalog: CatalogService) -> None:
    coll = catalog.collection("SARTestProject", "Compounds")
    service = CompoundService(coll)
    service.add(
        {
            "Name": "EX-001",
            "SMILES": "Nc1ncc(Cl)nc1F",
            "Turbi Solubility [mM]": 12.5,
        }
    )
    service.add(
        {
            "Name": "EX-empty",
            "SMILES": "",
        }
    )


def test_get_series_snapshot_shape(sar_repo):
    repo, catalog = sar_repo
    _seed_series(catalog)

    snapshot = repo.get_series_snapshot(
        "SARTestProject",
        "Compounds",
        assay_ids=["Turbi Solubility [mM]"],
    )
    data = snapshot.to_dict()

    assert data["source"]["system_id"] == "wetlabdb"
    assert data["series"]["project_id"] == "SARTestProject"
    assert data["series"]["id"] == "Compounds"
    assert len(data["compounds"]) == 2

    with_smiles = next(c for c in data["compounds"] if c["display_id"] == "EX-001")
    assert with_smiles["structure"]["format"] == "smiles"
    assert with_smiles["structure"]["value"] == "Nc1ncc(Cl)nc1F"
    assert with_smiles["structure"]["coordinates_2d_source"] is None
    assert with_smiles["structure"]["fingerprint"]

    measurement = with_smiles["measurements"][0]
    assert measurement["assay_id"] == "Turbi Solubility [mM]"
    assert measurement["qualifier"] == "="
    assert measurement["value"] == 12.5
    assert measurement["unit"] == "mM"

    empty_row = next(c for c in data["compounds"] if c["display_id"] == "EX-empty")
    assert empty_row["structure"]["value"] == ""
    assert empty_row["measurements"][0]["qualifier"] == "not_determined"
    assert empty_row["measurements"][0]["value"] is None

    assert data["assay_definitions"][0]["default_unit"] == "mM"


def test_snapshot_revision_stable_when_data_unchanged(sar_repo):
    repo, catalog = sar_repo
    _seed_series(catalog)

    first = repo.get_series_snapshot(
        "SARTestProject",
        "Compounds",
        assay_ids=["Turbi Solubility [mM]"],
    )
    second = repo.get_series_snapshot(
        "SARTestProject",
        "Compounds",
        assay_ids=["Turbi Solubility [mM]"],
    )

    assert first.source.revision == second.source.revision
    assert first.to_dict()["source"]["revision"] == second.to_dict()["source"]["revision"]


def test_search_projects_and_list_series(sar_repo):
    repo, catalog = sar_repo
    catalog.create_collection("SARTestProject", "SeriesB")

    projects = repo.search_projects("sar", cursor=None, limit=10)
    assert any(p.id == "SARTestProject" for p in projects.items)

    series = repo.list_series("SARTestProject", cursor=None, limit=10)
    names = {s.id for s in series.items}
    assert "Compounds" in names
    assert "SeriesB" in names


def test_get_structure_revision(sar_repo):
    repo, catalog = sar_repo
    _seed_series(catalog)
    coll = catalog.collection("SARTestProject", "Compounds")
    cid = CompoundService(coll).list_all()[0]["_id"]
    cid_str = str(cid)

    rev = repo.get_structure_revision("SARTestProject", "Compounds", cid_str)
    assert rev.compound_id == cid_str
    assert rev.format == "smiles"
    assert rev.fingerprint


def test_hidden_database_raises(sar_repo):
    repo, _catalog = sar_repo
    with pytest.raises(SarRepositoryError):
        repo.get_series_snapshot("wetlabdb_meta", "users", assay_ids=[])
