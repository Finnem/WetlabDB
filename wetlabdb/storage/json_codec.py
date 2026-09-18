"""JSON serialisation helpers shared by both backends."""

from __future__ import annotations

import json
from datetime import date, datetime

from wetlabdb.storage.ids import ObjectId


class MongoJSONEncoder(json.JSONEncoder):
    """JSON encoder that knows about :class:`ObjectId` and :class:`datetime`."""

    def default(self, obj):  # type: ignore[override]
        if isinstance(obj, ObjectId) or obj.__class__.__name__ == "ObjectId":
            return str(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


def local_json_default(obj):
    """Fallback for ``json.dump(default=...)`` used by the local backend."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)


__all__ = ["MongoJSONEncoder", "local_json_default"]
