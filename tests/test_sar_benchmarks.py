"""Smoke benchmarks for alignment batch sizes (Slice 7)."""

from __future__ import annotations

import time

import pytest

from wetlabdb.sar.hardening.limits import BENCHMARK_COMPOUND_COUNTS
from wetlabdb.sar.pipeline.fixed_core import run_same_scaffold


def _bench_case(n: int) -> dict:
    molecules = [
        {"id": f"B{i}", "smiles": f"COc1ccc(C{'C' * i})cc1"[:40] or "COc1ccccc1"}
        for i in range(n)
    ]
    # keep valid SMILES — use simple para substituents
    molecules = [{"id": f"B{i}", "smiles": "COc1ccc(C)cc1"} for i in range(n)]
    return {
        "id": f"bench-{n}",
        "comparison": {
            "mode": "same_scaffold",
            "reference": "B0",
            "core_smarts": "COc1ccccc1",
        },
        "molecules": molecules,
    }


@pytest.mark.parametrize("count", BENCHMARK_COMPOUND_COUNTS)
def test_same_scaffold_batch_smoke(count):
    case = _bench_case(count)
    start = time.perf_counter()
    result = run_same_scaffold(case)
    elapsed = time.perf_counter() - start
    assert result.status == "OPTIMAL"
    assert len(result.layouts) == count
    assert elapsed < 60.0, f"{count} compounds took {elapsed:.1f}s"
