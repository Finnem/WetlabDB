"""Certificate and completion policy (Slice 7 / S01–S07)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from wetlabdb.sar.hardening.vocabulary import (
    S01_OPTIMAL_COMPLETE,
    S02_ENUM_INCOMPLETE,
    S03_MCS_INCOMPLETE,
    S04_OPTIMIZE_INCOMPLETE,
    S05_INFEASIBLE,
    S06_RENDER_VALIDATION_FAILED,
    S07_CERTIFICATE_INVALID,
)
from wetlabdb.sar.pipeline.models import AlignmentResult


@dataclass(frozen=True)
class CompletionPolicy:
    status: str
    user_message: str
    certificate: str | None
    details: dict[str, Any]


def optimal_complete(*, certificate: str = "candidate_selection_optimal") -> CompletionPolicy:
    return CompletionPolicy(
        status="OPTIMAL",
        user_message=S01_OPTIMAL_COMPLETE,
        certificate=certificate,
        details={"completion": "S01"},
    )


def infeasible_in_template_set() -> CompletionPolicy:
    return CompletionPolicy(
        status="INFEASIBLE_OR_USER_VISIBLE_UNMATCHED",
        user_message=S05_INFEASIBLE,
        certificate=None,
        details={"completion": "S05"},
    )


def enumeration_incomplete() -> CompletionPolicy:
    return CompletionPolicy(
        status="VALID",
        user_message=S02_ENUM_INCOMPLETE,
        certificate=None,
        details={"completion": "S02"},
    )


def mcs_search_incomplete() -> CompletionPolicy:
    return CompletionPolicy(
        status="VALID",
        user_message=S03_MCS_INCOMPLETE,
        certificate=None,
        details={"completion": "S03"},
    )


def optimization_incomplete() -> CompletionPolicy:
    return CompletionPolicy(
        status="VALID",
        user_message=S04_OPTIMIZE_INCOMPLETE,
        certificate=None,
        details={"completion": "S04"},
    )


def render_validation_failure() -> CompletionPolicy:
    return CompletionPolicy(
        status="INFEASIBLE_OR_USER_VISIBLE_UNMATCHED",
        user_message=S06_RENDER_VALIDATION_FAILED,
        certificate=None,
        details={"completion": "S06"},
    )


def certificate_invalidated() -> CompletionPolicy:
    return CompletionPolicy(
        status="VALID",
        user_message=S07_CERTIFICATE_INVALID,
        certificate=None,
        details={"completion": "S07"},
    )


def apply_policy(result: AlignmentResult, policy: CompletionPolicy) -> AlignmentResult:
    merged_details = {**(result.details or {}), **policy.details}
    return AlignmentResult(
        case_id=result.case_id,
        status=policy.status,
        certificate=policy.certificate,
        user_message=policy.user_message,
        layouts=result.layouts,
        objective=result.objective,
        details=merged_details,
        unsupported_reason=result.unsupported_reason,
    )


def strip_certificate_from_draft(draft: dict[str, Any]) -> dict[str, Any]:
    """S07: edited draft must not retain an prior optimality certificate."""
    if not draft.get("certificate"):
        return draft
    out = dict(draft)
    out["certificate"] = None
    out["user_message"] = S07_CERTIFICATE_INVALID
    if out.get("status") == "OPTIMAL":
        out["status"] = "VALID"
    details = dict(out.get("details") or {})
    details["completion"] = "S07"
    details["certificate_invalidated"] = True
    out["details"] = details
    return out


def optimizer_result_from_policy(
    case_id: str,
    policy: CompletionPolicy,
    *,
    audit: dict[str, Any],
    selections: list | None = None,
    optimum: list[int] | None = None,
) -> dict[str, Any]:
    return {
        "id": case_id,
        "status": policy.status if policy.status != "INFEASIBLE_OR_USER_VISIBLE_UNMATCHED" else "INFEASIBLE",
        "user_message": policy.user_message,
        "certificate": policy.certificate,
        "optimum": optimum,
        "selections": selections or [],
        "evaluated": audit.get("evaluated", 0),
        "feasible": audit.get("feasible", 0),
        "details": policy.details,
    }


__all__ = [
    "CompletionPolicy",
    "apply_policy",
    "certificate_invalidated",
    "enumeration_incomplete",
    "infeasible_in_template_set",
    "mcs_search_incomplete",
    "optimization_incomplete",
    "optimal_complete",
    "optimizer_result_from_policy",
    "render_validation_failure",
    "strip_certificate_from_draft",
]
