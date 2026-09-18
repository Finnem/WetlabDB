"""Search service: combines storage + chemistry layers."""

from __future__ import annotations

from wetlabdb.chem.enumerate import enumerate_molecules_from_smarts
from wetlabdb.chem.similarity import (
    DEFAULT_METRIC,
    SimilarityHit,
    similarity_search,
)
from wetlabdb.chem.smiles import looks_like_smarts, parse_smiles
from wetlabdb.chem.substructure import SubstructureHit, substructure_search
from wetlabdb.storage.base import CollectionProto

# Deeply negative so McConnaughey (range [-1, 1]) still returns every hit
# when the UI asks to "sort all" rather than filter by cutoff.
SORT_ALL_CUTOFF = -2.0


class SearchService:
    """Run similarity / substructure searches against a compound collection."""

    def __init__(self, collection: CollectionProto) -> None:
        self._coll = collection

    def similarity(
        self,
        query: str,
        cutoff: float = 0.7,
        *,
        metric: str = DEFAULT_METRIC,
        sort_all: bool = False,
    ) -> list[SimilarityHit]:
        """Fingerprint similarity search.

        Accepts either a SMILES (single query) or a SMARTS pattern (the SMARTS
        is enumerated to a set of concrete molecules and the *max* similarity
        across that set is used per-document).

        ``metric`` selects the similarity coefficient used; see
        :data:`wetlabdb.chem.similarity.SIMILARITY_METRICS` for the supported
        names. Unknown values silently fall back to Tanimoto.
        """
        if not query:
            return []

        mol = parse_smiles(query)
        if mol is not None:
            query_mols = [mol]
        elif looks_like_smarts(query):
            query_mols = enumerate_molecules_from_smarts(query)
        else:
            query_mols = []

        if not query_mols:
            return []

        effective_cutoff = SORT_ALL_CUTOFF if sort_all else cutoff
        return similarity_search(
            self._coll.find(),
            query_mols,
            cutoff=effective_cutoff,
            metric=metric,
        )

    def substructure(self, query_smarts: str) -> list[SubstructureHit]:
        """Return documents whose ``SMILES`` contains ``query_smarts`` as a sub-structure."""
        if not query_smarts:
            return []
        return substructure_search(self._coll.find(), query_smarts)


__all__ = ["SORT_ALL_CUTOFF", "SearchService"]
