"""User-facing completion messages (handoff S01–S07)."""

from __future__ import annotations

# Status case IDs map to exact user-visible strings in sar_alignment_molecular_cases_v1.json
S01_OPTIMAL_COMPLETE = "Best layout proven within this template set"
S02_ENUM_INCOMPLETE = "Best found; search domain enumeration incomplete"
S03_MCS_INCOMPLETE = "Best found; MCS search incomplete"
S04_OPTIMIZE_INCOMPLETE = "Best found; optimization incomplete"
S05_INFEASIBLE = "No layout satisfies these constraints in this template set"
S06_RENDER_VALIDATION_FAILED = (
    "exclude candidate and re-solve or report validation failure"
)
S07_CERTIFICATE_INVALID = "previous certificate invalid for edited output"

STATUS_CASE_MESSAGES: dict[str, str] = {
    "S01": S01_OPTIMAL_COMPLETE,
    "S02": S02_ENUM_INCOMPLETE,
    "S03": S03_MCS_INCOMPLETE,
    "S04": S04_OPTIMIZE_INCOMPLETE,
    "S05": S05_INFEASIBLE,
    "S06": S06_RENDER_VALIDATION_FAILED,
    "S07": S07_CERTIFICATE_INVALID,
}

FORBIDDEN_STATUS_BY_CASE: dict[str, str] = {
    "S02": "OPTIMAL",
    "S03": "INFEASIBLE",
    "S04": "OPTIMAL",
    "S06": "certified export",
    "S07": "reuse previous certificate",
}

__all__ = [
    "FORBIDDEN_STATUS_BY_CASE",
    "S01_OPTIMAL_COMPLETE",
    "S02_ENUM_INCOMPLETE",
    "S03_MCS_INCOMPLETE",
    "S04_OPTIMIZE_INCOMPLETE",
    "S05_INFEASIBLE",
    "S06_RENDER_VALIDATION_FAILED",
    "S07_CERTIFICATE_INVALID",
    "STATUS_CASE_MESSAGES",
]
