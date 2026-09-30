"""Read-only WetlabDB adapter for SAR SeriesSnapshot boundaries."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, TypeVar

from wetlabdb.schema.compound import COMPOUND_FORM
from wetlabdb.services.catalog import CatalogError, CatalogService
from wetlabdb.services.compounds import CompoundService
from wetlabdb.sar.fingerprints import (
    compound_revision,
    snapshot_revision,
    structure_fingerprint,
)
from wetlabdb.sar.models import (
    AssayDefinition,
    CompoundRecord,
    MeasurementRecord,
    Page,
    ProjectSummary,
    SeriesInfo,
    SeriesSnapshot,
    SeriesSummary,
    SnapshotSource,
    StructureRecord,
    StructureRevision,
)

SYSTEM_ID = "wetlabdb"
DEFAULT_PAGE_SIZE = 50
MAX_SNAPSHOT_COMPOUNDS = 200

INVENTORY_FIELDS = frozenset(
    {"Name", "alternative Name", "SMILES", "CAS Nr", "Storage Location"}
)

T = TypeVar("T")
_UNIT_IN_NAME = re.compile(r"\s*\[([^\]]+)\]\s*$")


class SarRepositoryError(ValueError):
    """Invalid project/series or adapter input."""


def _doc_id(doc: dict) -> str:
    raw = doc.get("_id")
    return str(raw) if raw is not None else ""


def _display_id(doc: dict, compound_id: str) -> str:
    name = str(doc.get("Name") or "").strip()
    if name:
        return name
    cas = str(doc.get("CAS Nr") or "").strip()
    if cas:
        return cas
    return compound_id


def parse_unit_from_field_name(field_name: str) -> str | None:
    match = _UNIT_IN_NAME.search(field_name)
    if match:
        return match.group(1).strip()
    return None


def _field_default(field_name: str) -> Any:
    info = COMPOUND_FORM.get(field_name)
    if info is None:
        return None
    return info.get("default")


def _field_type(field_name: str) -> str | None:
    info = COMPOUND_FORM.get(field_name)
    if info is None:
        return None
    return info.get("type")


def _raw_assay_value(doc: dict, assay_id: str) -> Any:
    if assay_id not in doc and assay_id not in COMPOUND_FORM:
        return None
    return doc.get(assay_id)


def _is_unset_assay_value(assay_id: str, value: Any) -> bool:
    if value is None:
        return True
    field_type = _field_type(assay_id)
    default = _field_default(assay_id)
    if field_type == "float":
        try:
            return float(value) == float(default)
        except (TypeError, ValueError):
            return False
    if field_type == "boolean":
        return value is False and default is False
    if field_type == "string":
        return str(value).strip() == str(default or "").strip()
    return value == default


def _measurement_from_field(
    doc: dict,
    assay_id: str,
    compound_rev: str,
) -> MeasurementRecord:
    raw = _raw_assay_value(doc, assay_id)
    unit = parse_unit_from_field_name(assay_id)
    field_type = _field_type(assay_id)

    if _is_unset_assay_value(assay_id, raw):
        return MeasurementRecord(
            assay_id=assay_id,
            value=None,
            qualifier="not_determined",
            unit=unit,
            uncertainty=None,
            display_value="—",
            revision=compound_rev,
        )

    if field_type == "boolean":
        numeric = 1.0 if bool(raw) else 0.0
        return MeasurementRecord(
            assay_id=assay_id,
            value=numeric,
            qualifier="=",
            unit=None,
            uncertainty=None,
            display_value="yes" if bool(raw) else "no",
            revision=compound_rev,
        )

    if field_type == "float":
        numeric = float(raw)
        display = str(numeric)
        return MeasurementRecord(
            assay_id=assay_id,
            value=numeric,
            qualifier="=",
            unit=unit,
            uncertainty=None,
            display_value=display,
            revision=compound_rev,
        )

    display = str(raw)
    return MeasurementRecord(
        assay_id=assay_id,
        value=None,
        qualifier="=",
        unit=unit,
        uncertainty=None,
        display_value=display,
        revision=compound_rev,
    )


def _assay_values_for_revision(doc: dict, assay_ids: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for assay_id in assay_ids:
        out[assay_id] = _raw_assay_value(doc, assay_id)
    return out


def _assay_definition(assay_id: str) -> AssayDefinition:
    return AssayDefinition(
        id=assay_id,
        name=assay_id,
        description=None,
        default_unit=parse_unit_from_field_name(assay_id),
        conditions={},
    )


def _compound_record(doc: dict, assay_ids: list[str]) -> CompoundRecord:
    compound_id = _doc_id(doc)
    smiles = str(doc.get("SMILES") or "")
    assay_payload = _assay_values_for_revision(doc, assay_ids)
    rev = compound_revision(compound_id, smiles, assay_payload)
    structure = StructureRecord(
        format="smiles",
        value=smiles,
        fingerprint=structure_fingerprint(smiles),
        coordinates_2d_source=None,
    )
    measurements = [_measurement_from_field(doc, aid, rev) for aid in assay_ids]
    return CompoundRecord(
        id=compound_id,
        display_id=_display_id(doc, compound_id),
        revision=rev,
        structure=structure,
        measurements=measurements,
    )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _page_slice(items: list[T], cursor: str | None, limit: int) -> Page[T]:
    start = 0
    if cursor:
        try:
            start = int(cursor)
        except ValueError as exc:
            raise SarRepositoryError("Invalid cursor") from exc
        if start < 0:
            raise SarRepositoryError("Invalid cursor")
    end = start + max(1, min(limit, DEFAULT_PAGE_SIZE * 4))
    chunk = items[start:end]
    next_cursor = str(end) if end < len(items) else None
    return Page(items=chunk, next_cursor=next_cursor)


class WetlabDBCompoundRepository:
    """Maps catalog + compound services to SAR read contracts."""

    def __init__(self, catalog: CatalogService) -> None:
        self._catalog = catalog

    def search_projects(
        self,
        query: str,
        cursor: str | None,
        limit: int,
    ) -> Page[ProjectSummary]:
        names = self._catalog.list_databases()
        term = (query or "").strip().lower()
        if term:
            names = [n for n in names if term in n.lower()]
        summaries = [ProjectSummary(id=n, name=n) for n in names]
        return _page_slice(summaries, cursor, limit or DEFAULT_PAGE_SIZE)

    def list_series(
        self,
        project_id: str,
        cursor: str | None,
        limit: int,
    ) -> Page[SeriesSummary]:
        try:
            names = self._catalog.list_collections(project_id)
        except CatalogError as exc:
            raise SarRepositoryError(str(exc)) from exc
        summaries = [
            SeriesSummary(id=n, project_id=project_id, name=n) for n in names
        ]
        return _page_slice(summaries, cursor, limit or DEFAULT_PAGE_SIZE)

    def get_series_snapshot(
        self,
        project_id: str,
        series_id: str,
        assay_ids: list[str],
        compound_ids: list[str] | None = None,
    ) -> SeriesSnapshot:
        try:
            coll = self._catalog.collection(project_id, series_id)
        except CatalogError as exc:
            raise SarRepositoryError(str(exc)) from exc
        service = CompoundService(coll)
        docs = service.list_all()
        if compound_ids:
            wanted = {str(cid) for cid in compound_ids}
            docs = [d for d in docs if _doc_id(d) in wanted]
        elif len(docs) > MAX_SNAPSHOT_COMPOUNDS:
            raise SarRepositoryError(
                f"Series contains {len(docs)} compounds; "
                f"select explicit compound ids (max {MAX_SNAPSHOT_COMPOUNDS} without selection)"
            )
        if len(docs) > MAX_SNAPSHOT_COMPOUNDS:
            raise SarRepositoryError(
                f"Selection exceeds maximum snapshot size ({MAX_SNAPSHOT_COMPOUNDS})"
            )
        ordered_assays = list(dict.fromkeys(assay_ids))
        compounds = [_compound_record(doc, ordered_assays) for doc in docs]
        revs = [c.revision for c in compounds]
        source = SnapshotSource(
            system_id=SYSTEM_ID,
            snapshot_at=_utc_now_iso(),
            revision=snapshot_revision(revs),
        )
        series = SeriesInfo(
            id=series_id,
            project_id=project_id,
            name=series_id,
            description=None,
        )
        definitions = [_assay_definition(aid) for aid in ordered_assays]
        return SeriesSnapshot(
            source=source,
            series=series,
            compounds=compounds,
            assay_definitions=definitions,
        )

    def get_compounds(
        self,
        project_id: str,
        series_id: str,
        compound_ids: list[str],
        assay_ids: list[str],
    ) -> list[CompoundRecord]:
        try:
            coll = self._catalog.collection(project_id, series_id)
        except CatalogError as exc:
            raise SarRepositoryError(str(exc)) from exc
        service = CompoundService(coll)
        ordered_assays = list(dict.fromkeys(assay_ids))
        out: list[CompoundRecord] = []
        for cid in compound_ids:
            doc = service.get(cid)
            if doc is None:
                continue
            out.append(_compound_record(doc, ordered_assays))
        return out

    def get_structure_revision(
        self,
        project_id: str,
        series_id: str,
        compound_id: str,
    ) -> StructureRevision:
        records = self.get_compounds(
            project_id,
            series_id,
            [compound_id],
            assay_ids=[],
        )
        if not records:
            raise SarRepositoryError("Compound not found")
        rec = records[0]
        return StructureRevision(
            compound_id=rec.id,
            revision=rec.revision,
            fingerprint=rec.structure.fingerprint,
            format=rec.structure.format,
            value=rec.structure.value,
        )


def list_assay_field_ids() -> list[str]:
    """Lab/assay columns from the shared compound form (not inventory fields)."""
    return [name for name in COMPOUND_FORM if name not in INVENTORY_FIELDS]


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "INVENTORY_FIELDS",
    "MAX_SNAPSHOT_COMPOUNDS",
    "SarRepositoryError",
    "SYSTEM_ID",
    "WetlabDBCompoundRepository",
    "list_assay_field_ids",
    "parse_unit_from_field_name",
]
