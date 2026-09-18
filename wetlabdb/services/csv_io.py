"""CSV import/export helpers extracted from the original UI methods.

These are pure functions taking a :class:`CollectionProto` (no Tk, no
``filedialog``), which makes them straightforward to test.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Iterable, Sequence

import pandas as pd

from wetlabdb.storage.base import CollectionProto


@dataclass
class CsvImportSummary:
    """Outcome of :func:`import_csv` -- counts of created vs updated rows."""

    created: int = 0
    updated: int = 0

    @property
    def total(self) -> int:
        return self.created + self.updated


def _coerce_value(value):
    """Convert a single pandas/numpy value into something JSON-friendly."""
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def import_csv(
    collection: CollectionProto,
    df: pd.DataFrame,
    identifier_col: str,
    data_cols: Sequence[str],
) -> CsvImportSummary:
    """Upsert each row of ``df`` into ``collection`` keyed by ``identifier_col``.

    * NaN values in ``data_cols`` are *skipped* rather than overwriting existing
      data.
    * NaN values in the identifier column cause the row to be skipped entirely.
    * NumPy scalar types are coerced to native Python types so that the JSON
      backend can serialise them.
    """
    summary = CsvImportSummary()

    for _, row in df.iterrows():
        raw_id = row[identifier_col]
        if pd.isna(raw_id):
            continue
        identifier = str(raw_id)

        doc_data: dict = {}
        for col in data_cols:
            value = row[col]
            if pd.isna(value):
                continue
            doc_data[col] = _coerce_value(value)

        query = {identifier_col: identifier}
        if collection.find_one(query) is not None:
            collection.update_one(query, {"$set": doc_data})
            summary.updated += 1
        else:
            doc_data[identifier_col] = identifier
            collection.insert_one(doc_data)
            summary.created += 1

    return summary


def export_csv_text(
    rows: Iterable[Sequence],
    headers: Sequence[str],
) -> str:
    """Return UTF-8 CSV text with the given header row."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(list(headers))
    for row in rows:
        writer.writerow(list(row))
    return buf.getvalue()


def export_csv(
    file_path: str,
    rows: Iterable[Sequence],
    headers: Sequence[str],
) -> None:
    """Write ``rows`` to ``file_path`` as UTF-8 CSV with the given header row.

    ``rows`` is any iterable of equal-length sequences (the row contents).
    """
    with open(file_path, "w", encoding="utf-8", newline="") as f:
        f.write(export_csv_text(rows, headers))


__all__ = ["CsvImportSummary", "export_csv", "export_csv_text", "import_csv"]
