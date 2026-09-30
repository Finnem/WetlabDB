"""High-level CRUD over a compound collection.

The service binds to one :class:`CollectionProto` and exposes a small,
intent-revealing API (``add``, ``get``, ``update``, ``delete``, ...) that the
UI can call without having to know about ``_id`` coercion.
"""

from __future__ import annotations

from typing import Iterable

from wetlabdb.services.compound_meta import DELETED_AT, DELETED_BY, is_soft_deleted, utc_now_iso
from wetlabdb.storage.base import CollectionProto
from wetlabdb.storage.ids import coerce_id


class CompoundService:
    """CRUD facade for a single compound collection."""

    def __init__(self, collection: CollectionProto) -> None:
        self._coll = collection

    @property
    def collection(self) -> CollectionProto:
        return self._coll

    @staticmethod
    def _active_only(docs: list[dict]) -> list[dict]:
        return [d for d in docs if not is_soft_deleted(d)]

    def list_all(self, *, include_deleted: bool = False) -> list[dict]:
        docs = self._coll.find()
        if include_deleted:
            return docs
        return self._active_only(docs)

    def list_deleted(self) -> list[dict]:
        return [d for d in self._coll.find() if is_soft_deleted(d)]

    def list_filtered(
        self,
        q: str | None = None,
        column: str | None = None,
        *,
        include_deleted: bool = False,
    ) -> list[dict]:
        """Case-insensitive substring filter matching the Tk table search."""
        docs = self.list_all(include_deleted=include_deleted)
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

    def find(self, filter: dict | None = None, *, include_deleted: bool = False) -> list[dict]:
        docs = self._coll.find(filter or {})
        if include_deleted:
            return docs
        return self._active_only(docs)

    def find_one(self, filter: dict | None = None, *, include_deleted: bool = False) -> dict | None:
        doc = self._coll.find_one(filter or {})
        if doc is None:
            return None
        if not include_deleted and is_soft_deleted(doc):
            return None
        return doc

    def find_one_active_by_fields(self, query: dict) -> dict | None:
        """First non-deleted document matching equality ``query``."""
        for doc in self._coll.find(query):
            if not is_soft_deleted(doc):
                return doc
        return None

    def get(self, doc_id: object, *, include_deleted: bool = False) -> dict | None:
        coerced = coerce_id(doc_id)
        if coerced is None:
            return None
        doc = self._coll.find_one({"_id": coerced})
        if doc is None:
            return None
        if not include_deleted and is_soft_deleted(doc):
            return None
        return doc

    def add(self, data: dict) -> str:
        payload = dict(data)
        payload.pop(DELETED_AT, None)
        payload.pop(DELETED_BY, None)
        return self._coll.insert_one(payload).inserted_id

    def update(self, doc_id: object, data: dict, *, unset: Iterable[str] = ()) -> bool:
        coerced = coerce_id(doc_id)
        if coerced is None:
            return False
        if self.get(doc_id) is None:
            return False
        update_doc: dict = {}
        payload = dict(data)
        payload.pop(DELETED_AT, None)
        payload.pop(DELETED_BY, None)
        if payload:
            update_doc["$set"] = payload
        unset_list = [k for k in unset if k not in (DELETED_AT, DELETED_BY)]
        if unset_list:
            update_doc["$unset"] = unset_list
        if not update_doc:
            return False
        result = self._coll.update_one({"_id": coerced}, update_doc)
        return result.modified_count > 0

    def soft_delete(self, doc_id: object, *, actor: str) -> bool:
        coerced = coerce_id(doc_id)
        if coerced is None:
            return False
        doc = self._coll.find_one({"_id": coerced})
        if doc is None or is_soft_deleted(doc):
            return False
        result = self._coll.update_one(
            {"_id": coerced},
            {"$set": {DELETED_AT: utc_now_iso(), DELETED_BY: actor}},
        )
        return result.modified_count > 0

    def restore(self, doc_id: object) -> bool:
        coerced = coerce_id(doc_id)
        if coerced is None:
            return False
        doc = self._coll.find_one({"_id": coerced})
        if doc is None or not is_soft_deleted(doc):
            return False
        result = self._coll.update_one(
            {"_id": coerced},
            {"$unset": [DELETED_AT, DELETED_BY]},
        )
        return result.modified_count > 0

    def hard_delete(self, doc_id: object) -> bool:
        coerced = coerce_id(doc_id)
        if coerced is None:
            return False
        return self._coll.delete_one({"_id": coerced}).deleted_count > 0

    def delete(self, doc_id: object) -> bool:
        """Physical delete (legacy); prefer :meth:`soft_delete` from HTTP layer."""
        return self.hard_delete(doc_id)

    def count_active(self) -> int:
        counter = getattr(self._coll, "count_active_documents", None)
        if callable(counter):
            return int(counter())
        return len(self.list_all())

    def list_paginated(
        self,
        *,
        q: str | None = None,
        column: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        fields: list[str] | None = None,
    ):
        from wetlabdb.services.compound_fields import mongo_projection, project_documents
        from wetlabdb.services.compound_list import (
            DEFAULT_COMPOUND_PAGE_SIZE,
            paginate_compounds,
        )

        def _finish(page):
            page.compounds = project_documents(page.compounds, fields)
            return page

        proj = mongo_projection(fields) if fields else None

        term = (q or "").strip()
        col = (column or "").strip()
        has_text_filter = bool(term) or (col and col.lower() != "all")

        if limit is None and not cursor:
            return _finish(
                paginate_compounds(self.list_filtered(q=q, column=column), limit=None, cursor=None)
            )

        capped = max(1, min(int(limit or DEFAULT_COMPOUND_PAGE_SIZE), 500))

        if has_text_filter:
            if term:
                find_query_page = getattr(self._coll, "find_query_page", None)
                server_query = getattr(self._coll, "supports_server_query", None)
                if callable(find_query_page) and callable(server_query) and server_query():
                    from wetlabdb.services.compound_list import CompoundPage
                    from wetlabdb.storage.compound_queries import build_compound_text_query

                    qdict = build_compound_text_query(q, column)
                    docs = find_query_page(
                        qdict, limit=capped, after_id=cursor, projection=proj
                    )
                    total = int(self._coll.count_documents(qdict))
                    next_cursor = str(docs[-1]["_id"]) if len(docs) >= capped else None
                    return _finish(
                        CompoundPage(compounds=docs, next_cursor=next_cursor, total=total)
                    )
            return _finish(
                paginate_compounds(
                    self.list_filtered(q=q, column=column),
                    limit=capped,
                    cursor=cursor,
                )
            )

        docs = self._coll.find_page(
            limit=capped,
            after_id=cursor,
            exclude_soft_deleted=True,
            projection=proj,
        )
        total = self.count_active()
        next_cursor = str(docs[-1]["_id"]) if len(docs) >= capped else None
        from wetlabdb.services.compound_list import CompoundPage

        return _finish(CompoundPage(compounds=docs, next_cursor=next_cursor, total=total))

    def count(self, filter: dict | None = None, *, include_deleted: bool = False) -> int:
        if include_deleted:
            return self._coll.count_documents(filter or {})
        return len(self.find(filter, include_deleted=False))


__all__ = ["CompoundService"]
