"""CSV import/export helpers extracted from the original UI methods.

These are pure functions taking a :class:`CollectionProto` (no Tk, no
``filedialog``), which makes them straightforward to test.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Any, Iterable, Literal, Sequence

import pandas as pd

from wetlabdb.schema.compound import CSV_IDENTIFIER_COLUMNS
from wetlabdb.storage.base import CollectionProto

CollisionMode = Literal["append", "overwrite"]


@dataclass
class CsvImportSummary:
    """Outcome of :func:`import_csv` -- counts of created vs collided rows."""

    created: int = 0
    updated: int = 0
    appended: int = 0

    @property
    def total(self) -> int:
        return self.created + self.updated + self.appended


def alternative_field(column: str) -> str:
    """Return the extra-field name used when appending a colliding value."""
    return f"alternative {column}"


def _coerce_value(value):
    """Convert a single pandas/numpy value into something JSON-friendly."""
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def _values_equal(left: Any, right: Any) -> bool:
    return str(left).strip() == str(right).strip()


def _merge_alternative(existing: Any, incoming: Any) -> Any:
    incoming_text = str(incoming).strip()
    if _is_blank(existing):
        return incoming
    parts = [part.strip() for part in str(existing).split(" / ") if part.strip()]
    if incoming_text not in parts:
        parts.append(incoming_text)
    return " / ".join(parts)


def _identity_values(existing: dict, identifier_col: str) -> set[str]:
    """Name / CAS / SMILES / match-key values already identifying this record."""
    identities: set[str] = set()
    keys = set(CSV_IDENTIFIER_COLUMNS)
    keys.add(identifier_col)
    for key in keys:
        value = existing.get(key)
        if not _is_blank(value):
            identities.add(str(value).strip())
        alt = existing.get(alternative_field(key))
        if _is_blank(alt):
            continue
        identities.update(
            part.strip() for part in str(alt).split(" / ") if part.strip()
        )
    return identities


def _append_patch(existing: dict, incoming: dict, identifier_col: str) -> dict:
    """Keep existing values; write collisions onto ``alternative {field}``.

    The match key and any value that already is this record's identity
    (Name, CAS, SMILES, or an existing alternative of those) are skipped.
    """
    identities = _identity_values(existing, identifier_col)
    patch: dict = {}
    for column, value in incoming.items():
        if column == identifier_col:
            continue
        incoming_text = str(value).strip()
        if incoming_text in identities:
            continue
        current = existing.get(column)
        if _is_blank(current):
            patch[column] = value
            identities.add(incoming_text)
            continue
        if _values_equal(current, value):
            continue
        alt = alternative_field(column)
        merged = _merge_alternative(existing.get(alt), value)
        if _values_equal(existing.get(alt), merged):
            continue
        patch[alt] = merged
        identities.add(incoming_text)
    return patch


def import_csv(
    collection: CollectionProto,
    df: pd.DataFrame,
    identifier_col: str,
    data_cols: Sequence[str],
    *,
    on_collision: CollisionMode = "append",
) -> CsvImportSummary:
    """Upsert each row of ``df`` into ``collection`` keyed by ``identifier_col``.

    * NaN values in ``data_cols`` are *skipped* rather than overwriting existing
      data.
    * NaN values in the identifier column cause the row to be skipped entirely.
    * NumPy scalar types are coerced to native Python types so that the JSON
      backend can serialise them.
    * ``on_collision="overwrite"`` replaces fields on an existing document
      (legacy upsert). ``on_collision="append"`` (default) leaves existing
      values in place and stores differing incoming values as
      ``alternative {field}``.
    """
    if on_collision not in ("append", "overwrite"):
        raise ValueError(f"Unknown on_collision mode: {on_collision!r}")

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
        existing = collection.find_one(query)
        if existing is not None:
            if on_collision == "overwrite":
                if doc_data:
                    collection.update_one(query, {"$set": doc_data})
                summary.updated += 1
            else:
                patch = _append_patch(existing, doc_data, identifier_col)
                if patch:
                    collection.update_one(query, {"$set": patch})
                    summary.appended += 1
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


__all__ = [
    "CollisionMode",
    "CsvImportSummary",
    "alternative_field",
    "export_csv",
    "export_csv_text",
    "import_csv",
]
