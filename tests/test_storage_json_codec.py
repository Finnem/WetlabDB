"""Tests for :mod:`wetlabdb.storage.json_codec`."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from wetlabdb.storage import MongoJSONEncoder, ObjectId, local_json_default


def test_encoder_handles_objectid():
    oid = ObjectId("5f8c1a3b2c0d4e5f6a7b8c9d")
    encoded = json.dumps({"_id": oid}, cls=MongoJSONEncoder)
    assert json.loads(encoded) == {"_id": "5f8c1a3b2c0d4e5f6a7b8c9d"}


def test_encoder_handles_foreign_objectid_class():
    """mongomock ships its own ObjectId; it must still serialise as a string."""

    class ObjectId:  # noqa: N801 - mimic bson/mongomock naming
        def __init__(self, value):
            self.value = value

        def __str__(self):
            return self.value

    encoded = json.dumps({"_id": ObjectId("abc")}, cls=MongoJSONEncoder)
    assert json.loads(encoded) == {"_id": "abc"}


def test_encoder_handles_datetime():
    when = datetime(2026, 4, 24, 12, 0, 0)
    encoded = json.dumps({"t": when}, cls=MongoJSONEncoder)
    assert json.loads(encoded) == {"t": "2026-04-24T12:00:00"}


def test_encoder_passes_through_primitives():
    payload = {"a": 1, "b": "two", "c": [1, 2, 3], "d": {"nested": True}, "e": None}
    assert json.loads(json.dumps(payload, cls=MongoJSONEncoder)) == payload


def test_encoder_raises_on_unknown_type():
    class Weird:
        pass

    with pytest.raises(TypeError):
        json.dumps({"x": Weird()}, cls=MongoJSONEncoder)


def test_local_json_default_handles_datetime_and_falls_back_to_str():
    when = datetime(2026, 4, 24, 12, 0, 0)
    assert local_json_default(when) == "2026-04-24T12:00:00"

    class Weird:
        def __str__(self) -> str:
            return "weird"

    assert local_json_default(Weird()) == "weird"
