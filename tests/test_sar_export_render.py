"""Export render smoke checks (Slice 7 visual regression gate)."""

from __future__ import annotations

import json
from pathlib import Path

from wetlabdb.chem.smiles import render_to_png_bytes
from wetlabdb.sar.pipeline.runner import run_molecular_case

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "sar_alignment_handoff_v1"
    / "sar_alignment_handoff_v1"
    / "tests"
    / "sar_alignment_molecular_cases_v1.json"
)


def test_m01_aligned_structures_render():
    case = next(c for c in json.loads(FIXTURE.read_text())["cases"] if c["id"] == "M01")
    result = run_molecular_case(case)
    assert result.status == "OPTIMAL"
    for layout in result.layouts:
        png = render_to_png_bytes(layout.smiles, width=220, height=180)
        assert png and len(png) > 500
