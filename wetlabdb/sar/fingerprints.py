"""Deterministic fingerprints for SAR adapter boundaries.

Does not canonicalize or standardize SMILES — hashes the stored text as-is.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def structure_fingerprint(smiles_text: str) -> str:
    """Fingerprint from the stored structure string (empty string allowed)."""
    return sha256_hex((smiles_text or "").encode("utf-8"))


def compound_revision(
    compound_id: str,
    smiles_text: str,
    assay_values: dict[str, Any],
) -> str:
    """Revision from immutable id, structure text, and selected assay payload."""
    payload = {
        "id": compound_id,
        "smiles": smiles_text or "",
        "assays": assay_values,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_hex(encoded)


def snapshot_revision(compound_revisions: list[str]) -> str:
    """Aggregate revision for a series snapshot."""
    joined = "\n".join(compound_revisions)
    return sha256_hex(joined.encode("utf-8"))


__all__ = [
    "compound_revision",
    "sha256_hex",
    "snapshot_revision",
    "structure_fingerprint",
]
