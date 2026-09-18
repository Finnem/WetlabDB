"""Fingerprint-based similarity search.

The search supports a handful of standard binary-fingerprint similarity
coefficients (Tanimoto, Dice, Cosine, ...). Tanimoto remains the historical
default so callers that don't pass ``metric`` get the same numbers they did
before this module gained metric support.

The fingerprint representation is currently the path-based RDKFingerprint,
which is what the rest of the codebase has always used; if we ever want to
swap in Morgan / MACCS / atom-pair fingerprints it should be a localised
change inside ``_fingerprint``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from rdkit import Chem, DataStructs

from wetlabdb.chem.smiles import parse_smiles


@dataclass
class SimilarityHit:
    """A single result from :func:`similarity_search`."""

    document: dict
    similarity: float


# Mapping of human-friendly metric names to the corresponding RDKit
# DataStructs callable. The order here is also the order shown in the UI
# dropdown, so Tanimoto stays first as the most familiar default.
SIMILARITY_METRICS: dict[str, Callable] = {
    "Tanimoto": DataStructs.TanimotoSimilarity,
    "Dice": DataStructs.DiceSimilarity,
    "Cosine": DataStructs.CosineSimilarity,
    "Sokal": DataStructs.SokalSimilarity,
    "Russel": DataStructs.RusselSimilarity,
    "Kulczynski": DataStructs.KulczynskiSimilarity,
    "McConnaughey": DataStructs.McConnaugheySimilarity,
    "Braun-Blanquet": DataStructs.BraunBlanquetSimilarity,
    "Rogot-Goldberg": DataStructs.RogotGoldbergSimilarity,
    "Asymmetric": DataStructs.AsymmetricSimilarity,
    # Tversky needs alpha/beta parameters; we expose a sensible default
    # (alpha = beta = 0.5, which makes Tversky reduce to Dice). Users who
    # need substructure-style asymmetric Tversky can call
    # ``DataStructs.TverskySimilarity`` directly with custom parameters.
    "Tversky": lambda a, b: DataStructs.TverskySimilarity(a, b, 0.5, 0.5),
}

DEFAULT_METRIC = "Tanimoto"


# Sensible per-metric "moderately similar" cutoffs for path-based
# RDKFingerprint at default settings. The numbers are calibrated so that a
# pair which scores ~0.7 under Tanimoto would also pass under any other
# metric, keeping the qualitative meaning of the slider stable across
# metric switches even though the absolute numbers differ.
#
# - Tanimoto = canonical 0.7.
# - Dice / Tversky(0.5,0.5) ~ 2T / (1+T) -> 0.82.
# - Cosine sits a touch above Tanimoto for typical fingerprint pairs.
# - Sokal = T / (2 - T) -> ~0.54 for T=0.7.
# - Russel includes the (huge) shared-zero count, so absolute values are
#   tiny -- 0.05 is already a reasonable "similar" line for sparse FPs.
# - Kulczynski = 0.5*(c/(a+c) + c/(b+c)) lands between Tanimoto and Dice.
# - McConnaughey can be negative; ~0.4 corresponds to Tanimoto ~0.7.
# - Braun-Blanquet conditions on the larger fingerprint (similar magnitude
#   to Tanimoto for matched-size fingerprints).
# - Rogot-Goldberg rewards shared 'off' bits, so values stay close to 1.
# - Asymmetric / "substructure-style" tends to score very high when one FP
#   is contained in the other.
METRIC_DEFAULT_CUTOFFS: dict[str, float] = {
    "Tanimoto": 0.70,
    "Dice": 0.82,
    "Cosine": 0.85,
    "Sokal": 0.54,
    "Russel": 0.05,
    "Kulczynski": 0.85,
    "McConnaughey": 0.40,
    "Braun-Blanquet": 0.70,
    "Rogot-Goldberg": 0.85,
    "Asymmetric": 0.85,
    "Tversky": 0.82,
}


# One- to two-line, user-facing descriptions used as tooltips in the search
# UI. Kept here next to the metric registry so adding a new metric only
# touches one file.
METRIC_DESCRIPTIONS: dict[str, str] = {
    "Tanimoto": (
        "Tanimoto: c / (a + b + c).\n"
        "The classical chemical-similarity coefficient. Range [0, 1]; "
        "~0.7 is a common threshold for 'similar' molecules."
    ),
    "Dice": (
        "Dice: 2c / (a + b + 2c).\n"
        "Counts shared bits twice. Always greater than or equal to Tanimoto "
        "for the same pair. Range [0, 1]."
    ),
    "Cosine": (
        "Cosine: c / sqrt((a+c)(b+c)).\n"
        "Cosine of the angle between the two binary fingerprint vectors. "
        "Slightly higher than Tanimoto for typical pairs. Range [0, 1]."
    ),
    "Sokal": (
        "Sokal: c / (c + 2(a + b)).\n"
        "Penalises mismatching bits twice; tends to score lower than "
        "Tanimoto for the same pair. Range [0, 1]."
    ),
    "Russel": (
        "Russel-Rao: c / (a + b + c + d).\n"
        "Includes shared 'off' bits in the denominator, so absolute values "
        "are tiny for sparse fingerprints (typical: 0.01-0.05). Range [0, 1]."
    ),
    "Kulczynski": (
        "Kulczynski-2: 0.5*(c/(a+c) + c/(b+c)).\n"
        "Average of two asymmetric overlaps -- how much of the query is in "
        "the target and vice versa. Range [0, 1]."
    ),
    "McConnaughey": (
        "McConnaughey: (c(a+b+c) - ab) / ((a+c)(b+c)).\n"
        "Can return negative scores for genuinely dissimilar pairs. "
        "Range [-1, 1]."
    ),
    "Braun-Blanquet": (
        "Braun-Blanquet: c / max(a+c, b+c).\n"
        "Conservative -- conditions on the larger fingerprint, so it is "
        "sensitive to size differences between molecules. Range [0, 1]."
    ),
    "Rogot-Goldberg": (
        "Rogot-Goldberg: 0.5*(c/(a+b+c) + d/(a+b+d)).\n"
        "Rewards both shared 'on' and shared 'off' bits, so scores stay "
        "close to 1 for typical sparse fingerprint pairs. Range [0, 1]."
    ),
    "Asymmetric": (
        "Asymmetric: c / min(a+c, b+c).\n"
        "Substructure-style score: high when the smaller fingerprint is "
        "mostly contained in the larger. Range [0, 1]."
    ),
    "Tversky": (
        "Tversky(alpha=0.5, beta=0.5): c / (alpha*a + beta*b + c).\n"
        "Generalised Dice / Tanimoto. Exposed here in the symmetric form, "
        "which is identical to Dice. Range [0, 1]."
    ),
}


def _resolve_metric(metric):
    """Coerce a metric name (or callable) into a similarity callable.

    Unknown names fall back to the default rather than raising, so a stale
    config value can't break search outright -- the worst that happens is
    the user gets Tanimoto numbers when they asked for "Foo".
    """
    if callable(metric):
        return metric
    if isinstance(metric, str) and metric in SIMILARITY_METRICS:
        return SIMILARITY_METRICS[metric]
    return SIMILARITY_METRICS[DEFAULT_METRIC]


def _fingerprint(mol):
    """Compute the fingerprint we use for similarity. Returns ``None`` on failure."""
    if mol is None:
        return None
    try:
        return Chem.RDKFingerprint(mol)
    except Exception:
        return None


def compute_similarity(query, target, *, metric: str = DEFAULT_METRIC) -> float:
    """Similarity between two RDKit molecules under the given metric.

    Returns ``0.0`` if either side is ``None``, fingerprinting fails, or the
    metric callable raises (e.g. on degenerate empty fingerprints). McConnaughey
    can produce negative values in [-1, 1]; all other supported metrics live
    in [0, 1].
    """
    if query is None or target is None:
        return 0.0
    q_fp = _fingerprint(query)
    t_fp = _fingerprint(target)
    if q_fp is None or t_fp is None:
        return 0.0
    metric_fn = _resolve_metric(metric)
    try:
        return float(metric_fn(q_fp, t_fp))
    except Exception:
        return 0.0


def tanimoto_similarity(query, target) -> float:
    """Backwards-compatible Tanimoto wrapper.

    Kept so older callers and tests don't need to be rewritten; new code
    should prefer :func:`compute_similarity` with an explicit ``metric``.
    """
    return compute_similarity(query, target, metric="Tanimoto")


def similarity_search(
    documents: Iterable[dict],
    query_mols: list,
    cutoff: float = 0.7,
    *,
    smiles_field: str = "SMILES",
    metric: str = DEFAULT_METRIC,
) -> list[SimilarityHit]:
    """Score every document against ``query_mols`` and filter by ``cutoff``.

    The score for each document is the *maximum* similarity over all
    queries (so a SMARTS pattern that enumerates to several concrete
    molecules is collapsed to its best-matching variant per target).
    Results are returned sorted by descending similarity.

    Query fingerprints are computed once and reused across every document,
    which is roughly an N-fold speedup over the previous implementation
    that re-fingerprinted the query inside the per-document loop.
    """
    metric_fn = _resolve_metric(metric)

    query_fps = [_fingerprint(q) for q in query_mols if q is not None]
    query_fps = [fp for fp in query_fps if fp is not None]
    if not query_fps:
        return []

    hits: list[SimilarityHit] = []
    for doc in documents:
        smiles = doc.get(smiles_field)
        if not smiles:
            continue
        target = parse_smiles(smiles)
        if target is None:
            continue
        target_fp = _fingerprint(target)
        if target_fp is None:
            continue
        best = float("-inf")
        for q_fp in query_fps:
            try:
                score = float(metric_fn(q_fp, target_fp))
            except Exception:
                continue
            if score > best:
                best = score
        if best == float("-inf"):
            continue
        if best >= cutoff:
            hits.append(SimilarityHit(document=doc, similarity=best))
    hits.sort(key=lambda h: h.similarity, reverse=True)
    return hits


__all__ = [
    "DEFAULT_METRIC",
    "METRIC_DEFAULT_CUTOFFS",
    "METRIC_DESCRIPTIONS",
    "SIMILARITY_METRICS",
    "SimilarityHit",
    "compute_similarity",
    "similarity_search",
    "tanimoto_similarity",
]
