"""Shared in-memory pagination for storage adapters."""

from __future__ import annotations

from wetlabdb.services.compound_meta import is_soft_deleted


def memory_find_page(
    docs: list[dict],
    *,
    limit: int,
    after_id: str | None = None,
    exclude_soft_deleted: bool = True,
) -> list[dict]:
    rows = list(docs)
    if exclude_soft_deleted:
        rows = [d for d in rows if not is_soft_deleted(d)]
    rows.sort(key=lambda d: str(d.get("_id", "")))
    start = 0
    if after_id:
        marker = str(after_id)
        start = next(
            (i for i, doc in enumerate(rows) if str(doc.get("_id", "")) > marker),
            len(rows),
        )
    capped = max(1, int(limit))
    return rows[start : start + capped]


__all__ = ["memory_find_page"]
