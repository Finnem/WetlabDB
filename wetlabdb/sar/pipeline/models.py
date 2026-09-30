"""Alignment pipeline result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MoleculeLayout:
    molecule_id: str
    smiles: str
    molblock: str | None = None
    core_atom_indices: list[int] = field(default_factory=list)


@dataclass
class AlignmentResult:
    case_id: str
    status: str
    certificate: str | None = None
    user_message: str = ""
    layouts: list[MoleculeLayout] = field(default_factory=list)
    objective: list[int] | None = None
    details: dict[str, Any] = field(default_factory=dict)
    unsupported_reason: str | None = None


__all__ = ["AlignmentResult", "MoleculeLayout"]
