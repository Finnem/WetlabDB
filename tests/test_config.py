"""Tests for :class:`wetlabdb.config.AppConfig`."""

from __future__ import annotations

import json

import pytest

from wetlabdb.config import AppConfig
from wetlabdb.storage import PYMONGO_AVAILABLE, default_local_data_dir


def test_defaults_match_environment():
    cfg = AppConfig()
    assert cfg.last_database is None
    assert cfg.last_collection is None
    assert cfg.visible_columns == []
    assert cfg.username == ""
    assert cfg.host_ip == "localhost"
    assert cfg.port == 27017
    assert cfg.auth_source == "admin"
    assert cfg.admin_access is False
    assert cfg.local_data_dir == default_local_data_dir()
    assert cfg.mode == ("remote" if PYMONGO_AVAILABLE else "local")


def test_load_missing_file_returns_defaults(tmp_path):
    cfg = AppConfig.load(str(tmp_path / "does_not_exist.json"))
    assert cfg == AppConfig()


def test_round_trip_save_and_load(tmp_path):
    path = str(tmp_path / "cfg.json")
    cfg = AppConfig(
        last_database="WetlabDB",
        last_collection="Compounds",
        visible_columns=["Name", "SMILES"],
        mode="local",
        local_data_dir=str(tmp_path),
        username="alice",
        host_ip="10.0.0.1",
        port=27018,
        auth_source="admin",
    )
    cfg.save(path)

    loaded = AppConfig.load(path)
    assert loaded == cfg


def test_unknown_keys_preserved_via_extras(tmp_path):
    path = tmp_path / "cfg.json"
    path.write_text(
        json.dumps(
            {
                "last_database": "X",
                "future_field": "from_a_newer_version",
                "another_future": [1, 2, 3],
            }
        ),
        encoding="utf-8",
    )

    cfg = AppConfig.load(str(path))
    assert cfg.last_database == "X"
    assert cfg.extras == {
        "future_field": "from_a_newer_version",
        "another_future": [1, 2, 3],
    }

    cfg.save(str(path))
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["future_field"] == "from_a_newer_version"
    assert on_disk["another_future"] == [1, 2, 3]


def test_load_invalid_json_returns_defaults(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not valid", encoding="utf-8")
    assert AppConfig.load(str(path)) == AppConfig()


def test_load_non_dict_returns_defaults(tmp_path):
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert AppConfig.load(str(path)) == AppConfig()


def test_to_dict_includes_all_fields():
    cfg = AppConfig()
    d = cfg.to_dict()
    assert set(AppConfig.field_names()).issubset(d.keys())
    assert "extras" not in d


def test_from_dict_partial_fills_defaults():
    cfg = AppConfig.from_dict({"last_database": "X"})
    assert cfg.last_database == "X"
    assert cfg.last_collection is None  # default
    assert cfg.visible_columns == []  # default


def test_atomic_save_does_not_leave_tmp_file(tmp_path):
    path = tmp_path / "cfg.json"
    AppConfig(last_database="X").save(str(path))
    files = sorted(p.name for p in tmp_path.iterdir())
    assert files == ["cfg.json"]


def test_from_dict_none_yields_defaults():
    assert AppConfig.from_dict(None) == AppConfig()
    assert AppConfig.from_dict({}) == AppConfig()


# ---------------------------------------------------------------------------
# Per-connection "last opened" memory
# ---------------------------------------------------------------------------
def test_last_selection_defaults_empty():
    cfg = AppConfig()
    assert cfg.last_selection_by_key == {}
    assert cfg.get_last_selection("remote:1.2.3.4:27017") is None


def test_set_and_get_last_selection_isolated_per_key():
    cfg = AppConfig()
    cfg.set_last_selection(
        "remote:host:27017",
        last_database="WetlabDB",
        last_collection="Compounds",
        visible_columns=["Name", "SMILES"],
    )
    cfg.set_last_selection(
        "local:/data/wetlab",
        last_database="lab_book",
        last_collection="experiments",
    )

    remote = cfg.get_last_selection("remote:host:27017")
    local = cfg.get_last_selection("local:/data/wetlab")
    assert remote == {
        "last_database": "WetlabDB",
        "last_collection": "Compounds",
        "visible_columns": ["Name", "SMILES"],
    }
    assert local == {
        "last_database": "lab_book",
        "last_collection": "experiments",
    }
    assert cfg.get_last_selection("remote:other:27017") is None


def test_set_last_selection_partial_update_does_not_clobber():
    cfg = AppConfig()
    cfg.set_last_selection(
        "k1",
        last_database="db1",
        last_collection="c1",
        visible_columns=["A"],
    )
    cfg.set_last_selection("k1", last_collection="c2")
    assert cfg.get_last_selection("k1") == {
        "last_database": "db1",
        "last_collection": "c2",
        "visible_columns": ["A"],
    }


def test_set_last_selection_ignores_empty_key():
    cfg = AppConfig()
    cfg.set_last_selection("", last_database="x")
    assert cfg.last_selection_by_key == {}
    assert cfg.get_last_selection("") is None


def test_get_last_selection_returns_copy():
    cfg = AppConfig()
    cfg.set_last_selection("k", last_database="db1")
    snapshot = cfg.get_last_selection("k")
    assert snapshot is not None
    snapshot["last_database"] = "mutated"
    # Mutation of the returned dict must not leak into the config.
    assert cfg.get_last_selection("k") == {"last_database": "db1"}


def test_last_selection_round_trips_through_save_load(tmp_path):
    path = str(tmp_path / "cfg.json")
    cfg = AppConfig()
    cfg.set_last_selection(
        "remote:1.2.3.4:27017",
        last_database="WetlabDB",
        last_collection="Compounds",
        visible_columns=["Name"],
    )
    cfg.set_last_selection(
        "local:/tmp/x",
        last_database="papers",
        last_collection="2025",
    )
    cfg.save(path)

    loaded = AppConfig.load(path)
    assert loaded.get_last_selection("remote:1.2.3.4:27017") == {
        "last_database": "WetlabDB",
        "last_collection": "Compounds",
        "visible_columns": ["Name"],
    }
    assert loaded.get_last_selection("local:/tmp/x") == {
        "last_database": "papers",
        "last_collection": "2025",
    }


def test_admin_access_round_trips(tmp_path):
    path = str(tmp_path / "cfg.json")
    AppConfig(admin_access=True).save(path)
    loaded = AppConfig.load(path)
    assert loaded.admin_access is True


def test_admin_access_default_after_legacy_load(tmp_path):
    """Configs written by older versions (no ``admin_access`` field) must
    load with the safe ``False`` default rather than crashing."""
    path = tmp_path / "cfg.json"
    path.write_text(
        json.dumps(
            {
                "last_database": "WetlabDB",
                "last_collection": "Compounds",
                "host_ip": "1.2.3.4",
                "port": "27017",
                "username": "alice",
                "auth_source": "admin",
            }
        ),
        encoding="utf-8",
    )
    cfg = AppConfig.load(str(path))
    assert cfg.admin_access is False


def test_legacy_config_without_per_key_still_loads(tmp_path):
    """A pre-migration config file (only legacy top-level fields) must load.

    Per-connection migration is performed lazily by the UI layer; AppConfig
    itself just needs to round-trip both shapes side-by-side.
    """
    path = tmp_path / "cfg.json"
    path.write_text(
        json.dumps(
            {
                "last_database": "WetlabDB",
                "last_collection": "Compounds",
                "visible_columns": ["Name", "SMILES"],
            }
        ),
        encoding="utf-8",
    )
    cfg = AppConfig.load(str(path))
    assert cfg.last_database == "WetlabDB"
    assert cfg.last_collection == "Compounds"
    assert cfg.visible_columns == ["Name", "SMILES"]
    assert cfg.last_selection_by_key == {}
