"""SMARTS-based substructure search."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from wetlabdb.chem.smiles import (
    parse_smarts,
    parse_smarts_for_search,
    parse_smiles,
)


@dataclass
class SubstructureHit:
    """A document whose ``SMILES`` matched a SMARTS query."""

    document: dict
    match_atoms: tuple[int, ...] = ()


def substructure_search(
    documents: Iterable[dict],
    query_smarts: str,
    *,
    smiles_field: str = "SMILES",
) -> list[SubstructureHit]:
    """Return every document whose ``smiles_field`` contains the SMARTS pattern.

    The query is run through :func:`parse_smarts_for_search`, which performs
    aromaticity perception on the SMARTS so that Kekulé-form patterns
    (e.g. the ``[#6]1=[#6]-[#6]=[#6]-[#6]=[#6]-1-*`` produced by the 2D
    drawing editor for "benzene + substituent") still match aromatic SMILES
    like ``c1ccccc1``.

    Returns an empty list (rather than raising) for unparsable SMARTS, so the
    caller can show an empty-result UI without special-casing exceptions.
    """
    query = parse_smarts_for_search(query_smarts)
    if query is None:
        return []

    hits: list[SubstructureHit] = []
    for doc in documents:
        smiles = doc.get(smiles_field)
        if not smiles:
            continue
        mol = parse_smiles(smiles)
        if mol is None:
            continue
        try:
            match = mol.GetSubstructMatch(query)
        except Exception:
            continue
        if match:
            hits.append(SubstructureHit(document=doc, match_atoms=tuple(match)))
    return hits


__all__ = [
    "SubstructureHit",
    "parse_smarts",
    "parse_smarts_for_search",
    "substructure_search",
]
