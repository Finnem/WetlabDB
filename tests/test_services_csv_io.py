"""Tests for :mod:`wetlabdb.services.csv_io`."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from wetlabdb.services import export_csv, import_csv
from wetlabdb.storage import LocalCollection


@pytest.fixture
def collection(tmp_path):
    return LocalCollection(str(tmp_path / "x.json"))


def test_import_creates_new_documents(collection):
    df = pd.DataFrame(
        {
            "Name": ["Aspirin", "Caffeine"],
            "SMILES": ["CC(=O)Oc1ccccc1C(=O)O", "CN1C=NC2=C1C(=O)N(C(=O)N2C)C"],
        }
    )
    summary = import_csv(collection, df, identifier_col="Name", data_cols=["SMILES"])
    assert summary.created == 2
    assert summary.updated == 0
    assert summary.total == 2
    assert collection.count_documents() == 2


def test_import_updates_existing_documents(collection):
    collection.insert_one({"Name": "Aspirin", "SMILES": "old"})
    df = pd.DataFrame({"Name": ["Aspirin"], "SMILES": ["new"]})
    summary = import_csv(collection, df, "Name", ["SMILES"])
    assert summary.created == 0
    assert summary.updated == 1
    assert collection.find_one({"Name": "Aspirin"})["SMILES"] == "new"


def test_import_skips_nan_in_identifier(collection):
    df = pd.DataFrame(
        {"Name": ["Aspirin", float("nan"), "Caffeine"], "SMILES": ["a", "b", "c"]}
    )
    summary = import_csv(collection, df, "Name", ["SMILES"])
    assert summary.created == 2  # the NaN row was skipped


def test_import_skips_nan_data_values(collection):
    collection.insert_one({"Name": "Aspirin", "Pure": True})
    df = pd.DataFrame({"Name": ["Aspirin"], "Pure": [float("nan")]})
    summary = import_csv(collection, df, "Name", ["Pure"])
    assert summary.updated == 1
    # NaN was skipped: existing value preserved.
    assert collection.find_one({"Name": "Aspirin"})["Pure"] is True


def test_import_coerces_numpy_types_to_native(collection):
    df = pd.DataFrame(
        {"Name": ["x"], "n": np.array([42], dtype=np.int64), "f": np.array([3.14])}
    )
    summary = import_csv(collection, df, "Name", ["n", "f"])
    assert summary.created == 1
    doc = collection.find_one({"Name": "x"})
    assert isinstance(doc["n"], int) and doc["n"] == 42
    assert isinstance(doc["f"], float) and doc["f"] == pytest.approx(3.14)


def test_export_csv_writes_utf8_with_headers(tmp_path):
    out = tmp_path / "out.csv"
    export_csv(
        str(out),
        rows=[["Aspirin", "CC(=O)O"], ["Caffeine", "CN1..."]],
        headers=["Name", "SMILES"],
    )
    text = out.read_text(encoding="utf-8")
    lines = text.strip().splitlines()
    assert lines[0] == "Name,SMILES"
    assert "Aspirin" in lines[1]
    assert "Caffeine" in lines[2]


def test_export_csv_empty_rows_writes_header_only(tmp_path):
    out = tmp_path / "out.csv"
    export_csv(str(out), rows=[], headers=["a", "b"])
    assert out.read_text(encoding="utf-8").strip() == "a,b"
