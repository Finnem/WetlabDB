"""Pure chemistry helpers built on RDKit.

Nothing in this package imports Tk; that makes everything here straightforward
to unit-test without spinning up a GUI.
"""

from __future__ import annotations

from wetlabdb.chem.enumerate import enumerate_molecules_from_smarts
from wetlabdb.chem.similarity import (
    DEFAULT_METRIC,
    METRIC_DEFAULT_CUTOFFS,
    METRIC_DESCRIPTIONS,
    SIMILARITY_METRICS,
    SimilarityHit,
    compute_similarity,
    similarity_search,
    tanimoto_similarity,
)
from wetlabdb.chem.smiles import (
    MoleculeKind,
    aromatize_query,
    canonicalize_smiles,
    is_pure_smiles,
    looks_like_smarts,
    mol_to_storage_string,
    molfile_to_storage_string,
    parse_molecule,
    parse_smarts_for_search,
    parse_smiles,
    perceive_aromaticity,
    render_to_png_bytes,
)
from wetlabdb.chem.substructure import (
    SubstructureHit,
    parse_smarts,
    substructure_search,
)

__all__ = [
    "DEFAULT_METRIC",
    "METRIC_DEFAULT_CUTOFFS",
    "METRIC_DESCRIPTIONS",
    "MoleculeKind",
    "SIMILARITY_METRICS",
    "SimilarityHit",
    "SubstructureHit",
    "aromatize_query",
    "canonicalize_smiles",
    "compute_similarity",
    "enumerate_molecules_from_smarts",
    "is_pure_smiles",
    "looks_like_smarts",
    "mol_to_storage_string",
    "molfile_to_storage_string",
    "parse_molecule",
    "parse_smarts",
    "parse_smarts_for_search",
    "parse_smiles",
    "perceive_aromaticity",
    "render_to_png_bytes",
    "similarity_search",
    "substructure_search",
    "tanimoto_similarity",
]
