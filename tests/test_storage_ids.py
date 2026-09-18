"""Tests for ``ObjectId`` handling and id helpers."""

from __future__ import annotations

import re

from wetlabdb.storage import ObjectId, PYMONGO_AVAILABLE, coerce_id, new_local_id

HEX24 = re.compile(r"^[0-9a-f]{24}$")


def test_new_local_id_is_24_char_hex():
    new = new_local_id()
    assert HEX24.match(new), f"{new!r} is not 24-char hex"


def test_new_local_id_is_unique_enough():
    ids = {new_local_id() for _ in range(1000)}
    assert len(ids) == 1000


def test_coerce_none():
    assert coerce_id(None) is None


def test_coerce_valid_hex_returns_objectid_when_pymongo_available():
    valid = "5f8c1a3b2c0d4e5f6a7b8c9d"
    coerced = coerce_id(valid)
    assert str(coerced) == valid
    if PYMONGO_AVAILABLE:
        from bson import ObjectId as _BsonObjectId

        assert isinstance(coerced, _BsonObjectId)


def test_coerce_invalid_falls_back_to_string():
    coerced = coerce_id("not-a-valid-objectid")
    assert isinstance(coerced, str)
    assert str(coerced) == "not-a-valid-objectid"


def test_coerce_idempotent_on_objectid_input():
    valid = "5f8c1a3b2c0d4e5f6a7b8c9d"
    once = coerce_id(valid)
    twice = coerce_id(once)
    assert str(once) == str(twice) == valid


def test_objectid_value_can_be_used_as_string():
    oid = ObjectId(new_local_id())
    s = str(oid)
    assert HEX24.match(s)
    # Should be hashable and equal to its string form when using the fallback.
    assert {oid: 1}  # doesn't raise
