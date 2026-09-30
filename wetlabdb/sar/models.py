"""Stable SAR read-model types aligned with the handoff SeriesSnapshot contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Page(Generic[T]):
    items: list[T]
    next_cursor: str | None


@dataclass(frozen=True)
class ProjectSummary:
    id: str
    name: str


@dataclass(frozen=True)
class SeriesSummary:
    id: str
    project_id: str
    name: str


@dataclass(frozen=True)
class SnapshotSource:
    system_id: str
    snapshot_at: str
    revision: str


@dataclass(frozen=True)
class SeriesInfo:
    id: str
    project_id: str
    name: str
    description: str | None = None


@dataclass(frozen=True)
class StructureRecord:
    format: str
    value: str
    fingerprint: str
    coordinates_2d_source: str | None


@dataclass(frozen=True)
class MeasurementRecord:
    assay_id: str
    value: float | None
    qualifier: str
    unit: str | None
    uncertainty: float | None
    display_value: str
    revision: str


@dataclass(frozen=True)
class AssayDefinition:
    id: str
    name: str
    description: str | None = None
    default_unit: str | None = None
    conditions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CompoundRecord:
    id: str
    display_id: str
    revision: str
    structure: StructureRecord
    measurements: list[MeasurementRecord]


@dataclass(frozen=True)
class SeriesSnapshot:
    source: SnapshotSource
    series: SeriesInfo
    compounds: list[CompoundRecord]
    assay_definitions: list[AssayDefinition]

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable dict matching database_adapter.schema.json shape."""
        return {
            "source": {
                "system_id": self.source.system_id,
                "snapshot_at": self.source.snapshot_at,
                "revision": self.source.revision,
            },
            "series": {
                "id": self.series.id,
                "project_id": self.series.project_id,
                "name": self.series.name,
                "description": self.series.description,
            },
            "compounds": [
                {
                    "id": c.id,
                    "display_id": c.display_id,
                    "revision": c.revision,
                    "structure": {
                        "format": c.structure.format,
                        "value": c.structure.value,
                        "fingerprint": c.structure.fingerprint,
                        "coordinates_2d_source": c.structure.coordinates_2d_source,
                    },
                    "measurements": [
                        {
                            "assay_id": m.assay_id,
                            "value": m.value,
                            "qualifier": m.qualifier,
                            "unit": m.unit,
                            "uncertainty": m.uncertainty,
                            "display_value": m.display_value,
                            "revision": m.revision,
                        }
                        for m in c.measurements
                    ],
                }
                for c in self.compounds
            ],
            "assay_definitions": [
                {
                    "id": a.id,
                    "name": a.name,
                    "description": a.description,
                    "default_unit": a.default_unit,
                    "conditions": a.conditions,
                }
                for a in self.assay_definitions
            ],
        }


@dataclass(frozen=True)
class StructureRevision:
    compound_id: str
    revision: str
    fingerprint: str
    format: str
    value: str


__all__ = [
    "AssayDefinition",
    "CompoundRecord",
    "MeasurementRecord",
    "Page",
    "ProjectSummary",
    "SeriesInfo",
    "SeriesSnapshot",
    "SeriesSummary",
    "SnapshotSource",
    "StructureRecord",
    "StructureRevision",
]
