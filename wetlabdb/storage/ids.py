"""ObjectId handling that works with or without ``pymongo`` installed.

When ``bson`` is importable we re-export the real ``bson.ObjectId``. Otherwise
we provide a string-subclass fallback so the rest of the codebase can keep
calling ``ObjectId(some_str)`` unconditionally.

``new_local_id`` mints a brand-new id appropriate for the active environment;
``coerce_id`` does best-effort wrapping when a stored id is being put into a
filter dict.
"""

from __future__ import annotations

import uuid

try:  # pragma: no cover - exercised by both branches in CI
    from bson import ObjectId  # type: ignore[assignment]

    PYMONGO_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised in standalone tests
    PYMONGO_AVAILABLE = False

    class ObjectId(str):  # type: ignore[no-redef]
        """Drop-in stand-in for :class:`bson.ObjectId` based on ``str``.

        Equality with the underlying string just works because we *are* a
        string; this lets the local backend store plain string ``_id`` values
        while the calling code keeps wrapping them in ``ObjectId(...)``.
        """

        def __new__(cls, value: object | None = None) -> "ObjectId":
            if value is None:
                value = uuid.uuid4().hex[:24]
            return super().__new__(cls, str(value))

        def __repr__(self) -> str:  # pragma: no cover - cosmetic
            return f"ObjectId('{self}')"


def new_local_id() -> str:
    """Mint a new ``_id`` for a standalone-mode document.

    When ``pymongo`` is installed we mint a real BSON ObjectId so that the
    value round-trips through ``ObjectId(id_str)`` without raising; otherwise
    we use a 24-character hex string in the same format.
    """
    if PYMONGO_AVAILABLE:
        return str(ObjectId())
    return uuid.uuid4().hex[:24]


def coerce_id(value: object) -> object:
    """Best-effort conversion of a stringified ``_id`` for filter use.

    Returns ``None`` for ``None`` input.

    If ``pymongo`` is available and the value parses as a valid ``ObjectId``
    we return a real :class:`bson.ObjectId`; otherwise we return ``str(value)``
    so that local-backend filters (which compare via ``str()`` equality) still
    match.
    """
    if value is None:
        return None
    if PYMONGO_AVAILABLE:
        try:
            return ObjectId(value)
        except Exception:
            return str(value)
    return str(value)


__all__ = [
    "ObjectId",
    "PYMONGO_AVAILABLE",
    "coerce_id",
    "new_local_id",
]
