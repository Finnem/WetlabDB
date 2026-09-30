"""Paginated compound listing (stable ``_id`` order)."""

from __future__ import annotations

from dataclasses import dataclass

from wetlabdb.services.compound_meta import is_soft_deleted

MAX_COMPOUND_PAGE_SIZE = 500
DEFAULT_COMPOUND_PAGE_SIZE = 200


@dataclass
class CompoundPage:
    compounds: list[dict]
    next_cursor: str | None
    total: int


def paginate_compounds(
    docs: list[dict],
    *,
    limit: int | None,
    cursor: str | None,
) -> CompoundPage:
    active = [d for d in docs if not is_soft_deleted(d)]
    active.sort(key=lambda d: str(d.get("_id", "")))
    total = len(active)

    if limit is None:
        return CompoundPage(compounds=active, next_cursor=None, total=total)

    capped = max(1, min(int(limit), MAX_COMPOUND_PAGE_SIZE))
    start = 0
    if cursor:
        cursor = str(cursor)
        start = next(
            (index for index, doc in enumerate(active) if str(doc.get("_id", "")) > cursor),
            len(active),
        )
    page = active[start : start + capped]
    next_cursor = None
    if start + capped < total and page:
        next_cursor = str(page[-1]["_id"])
    return CompoundPage(compounds=page, next_cursor=next_cursor, total=total)


__all__ = [
    "CompoundPage",
    "DEFAULT_COMPOUND_PAGE_SIZE",
    "MAX_COMPOUND_PAGE_SIZE",
    "paginate_compounds",
]
