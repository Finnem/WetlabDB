"""Molecular search routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel

from wetlabdb.api.deps import get_current_user, search_for
from wetlabdb.api.serialize import doc_row, serialize_doc
from wetlabdb.chem.similarity import (
    DEFAULT_METRIC,
    METRIC_DEFAULT_CUTOFFS,
    METRIC_DESCRIPTIONS,
    SIMILARITY_METRICS,
)
from wetlabdb.schema.compound import SEARCH_RESULT_COLUMNS
from wetlabdb.services.auth import User
from wetlabdb.services.csv_io import export_csv_text
from wetlabdb.services.search import SearchService

router = APIRouter()


class SimilarityBody(BaseModel):
    query: str
    cutoff: float = 0.7
    metric: str = DEFAULT_METRIC
    sort_all: bool = False


class SubstructureBody(BaseModel):
    query: str


def _hit_payload(hit) -> dict:
    doc = serialize_doc(hit.document) or {}
    return {"document": doc, "similarity": hit.similarity}


@router.get("/search/metrics")
def search_metrics(_: User = Depends(get_current_user)):
    return {
        "default": DEFAULT_METRIC,
        "metrics": list(SIMILARITY_METRICS.keys()),
        "cutoffs": METRIC_DEFAULT_CUTOFFS,
        "descriptions": METRIC_DESCRIPTIONS,
    }


@router.post("/databases/{database}/collections/{collection}/search/similarity")
def similarity_search(
    body: SimilarityBody,
    svc: SearchService = Depends(search_for),
    _: User = Depends(get_current_user),
):
    hits = svc.similarity(
        body.query,
        cutoff=body.cutoff,
        metric=body.metric,
        sort_all=body.sort_all,
    )
    return {"hits": [_hit_payload(h) for h in hits]}


@router.post("/databases/{database}/collections/{collection}/search/substructure")
def substructure_search(
    body: SubstructureBody,
    svc: SearchService = Depends(search_for),
    _: User = Depends(get_current_user),
):
    hits = svc.substructure(body.query)
    return {
        "hits": [
            {
                "document": serialize_doc(h.document),
                "match_atoms": list(h.match_atoms),
            }
            for h in hits
        ]
    }


@router.get(
    "/databases/{database}/collections/{collection}/search/similarity.csv"
)
def export_similarity_csv(
    query: str,
    cutoff: float = 0.7,
    metric: str = DEFAULT_METRIC,
    sort_all: bool = False,
    svc: SearchService = Depends(search_for),
    _: User = Depends(get_current_user),
):
    hits = svc.similarity(
        query, cutoff=cutoff, metric=metric, sort_all=sort_all
    )
    columns = [c for c in SEARCH_RESULT_COLUMNS if c != "Similarity"]
    rows = []
    for hit in hits:
        row = doc_row(hit.document, columns)
        row.append(f"{hit.similarity:.4f}")
        rows.append(row)
    text = export_csv_text(rows, SEARCH_RESULT_COLUMNS)
    return Response(
        content=text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="search_results.csv"'
        },
    )
