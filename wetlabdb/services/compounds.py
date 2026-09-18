"""High-level CRUD over a compound collection.

The service binds to one :class:`CollectionProto` and exposes a small,
intent-revealing API (``add``, ``get``, ``update``, ``delete``, ...) that the
UI can call without having to know about ``_id`` coercion.
"""

from __future__ import annotations

from typing import Iterable

from wetlabdb.storage.base import CollectionProto
from wetlabdb.storage.ids import coerce_id


class CompoundService:
    """CRUD facade for a single compound collection."""

    def __init__(self, collection: CollectionProto) -> None:
        self._coll = collection

    @property
    def collection(self) -> CollectionProto:
        return self._coll

    def list_all(self) -> list[dict]:
        return self._coll.find()

    def list_filtered(
        self,
        q: str | None = None,
        column: str | None = None,
    ) -> list[dict]:
        """Case-insensitive substring filter matching the Tk table search.

        ``column`` of ``None`` / ``""`` / ``"All"`` searches every field
        value in the document (including ``_id``, which appears as a
        table cell when visible). A specific column name searches only
        that field.
        """
        docs = self.list_all()
        term = (q or "").lower()
        if not term:
            return docs
        column = (column or "").strip()
        out: list[dict] = []
        for doc in docs:
            if not column or column.lower() == "all":
                if any(term in str(value).lower() for value in doc.values()):
                    out.append(doc)
            else:
                if term in str(doc.get(column, "")).lower():
                    out.append(doc)
        return out

    def find(self, filter: dict | None = None) -> list[dict]:
        return self._coll.find(filter or {})

    def find_one(self, filter: dict | None = None) -> dict | None:
        return self._coll.find_one(filter or {})

    def get(self, doc_id: object) -> dict | None:
        coerced = coerce_id(doc_id)
        if coerced is None:
            return None
        return self._coll.find_one({"_id": coerced})

    def add(self, data: dict) -> str:
        return self._coll.insert_one(dict(data)).inserted_id

    def update(self, doc_id: object, data: dict, *, unset: Iterable[str] = ()) -> bool:
        coerced = coerce_id(doc_id)
        if coerced is None:
            return False
        update_doc: dict = {}
        if data:
            update_doc["$set"] = dict(data)
        unset_list = list(unset)
        if unset_list:
            update_doc["$unset"] = unset_list
        if not update_doc:
            return False
        result = self._coll.update_one({"_id": coerced}, update_doc)
        return result.modified_count > 0

    def delete(self, doc_id: object) -> bool:
        coerced = coerce_id(doc_id)
        if coerced is None:
            return False
        return self._coll.delete_one({"_id": coerced}).deleted_count > 0

    def count(self, filter: dict | None = None) -> int:
        return self._coll.count_documents(filter or {})


__all__ = ["CompoundService"]
