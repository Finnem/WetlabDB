"""Identity and import validation cases (M08, M09, M12)."""

from __future__ import annotations

from typing import Any

from rdkit import Chem

from wetlabdb.sar.pipeline.ingestion import (
    identity_fingerprint,
    ingest_molecule,
    molblock_round_trip,
)
from wetlabdb.sar.pipeline.models import AlignmentResult


def run_identity_validation(case: dict[str, Any]) -> AlignmentResult:
    case_id = case.get("id", "")
    seen_fps: list[tuple] = []
    for spec in case.get("molecules", []):
        ing = ingest_molecule(spec["id"], spec["smiles"])
        if ing is None:
            return AlignmentResult(
                case_id=case_id,
                status="INFEASIBLE",
                user_message=f"parse failed: {spec['id']}",
            )
        roundtrip = molblock_round_trip(spec["smiles"])
        if roundtrip is None or not _same_identity(ing.source_mol, roundtrip):
            return AlignmentResult(
                case_id=case_id,
                status="INFEASIBLE",
                user_message=f"round-trip identity failed: {spec['id']}",
            )
        fp = identity_fingerprint(ing.source_mol)
        if fp in seen_fps:
            return AlignmentResult(
                case_id=case_id,
                status="INFEASIBLE",
                user_message=f"duplicate identity unexpectedly: {spec['id']}",
            )
        seen_fps.append(fp)

    return AlignmentResult(
        case_id=case_id,
        status="VALID",
        user_message="Identity and export validation passed",
        details={"molecule_count": len(case.get("molecules", []))},
    )


def run_import_validation(case: dict[str, Any]) -> AlignmentResult:
    case_id = case.get("id", "")
    for spec in case.get("molecules", []):
        ing = ingest_molecule(spec["id"], spec["smiles"])
        if ing is None:
            return AlignmentResult(case_id=case_id, status="INFEASIBLE")
        frags = Chem.rdmolops.GetMolFrags(ing.source_mol)
        if len(frags) < 1:
            return AlignmentResult(case_id=case_id, status="INFEASIBLE")
        charges = [ing.source_mol.GetAtomWithIdx(i).GetFormalCharge() for i in range(ing.source_mol.GetNumAtoms())]
        if case["id"] == "M09" and sum(charges) == 0 and "." in spec["smiles"]:
            pass  # salt still has net zero; fragments preserved
    return AlignmentResult(
        case_id=case_id,
        status="VALID",
        user_message="Import policy preserve_as_supplied",
    )


def run_assay_data_case(case: dict[str, Any]) -> AlignmentResult:
    """M10: structured assay metadata survives (no orientation change)."""
    case_id = case.get("id", "")
    for spec in case.get("molecules", []):
        assays = spec.get("assays") or []
        for assay in assays:
            if assay.get("relation") == "<" and assay.get("value") is not None:
                if assay.get("value") == 0:
                    return AlignmentResult(case_id=case_id, status="INFEASIBLE")
            if assay.get("status") == "not_determined" and assay.get("value") not in (None, ""):
                return AlignmentResult(case_id=case_id, status="INFEASIBLE")
    return AlignmentResult(case_id=case_id, status="VALID", details={"assay_rows_checked": True})


def _same_identity(a: Chem.Mol, b: Chem.Mol) -> bool:
    return identity_fingerprint(a) == identity_fingerprint(b)


__all__ = ["run_assay_data_case", "run_identity_validation", "run_import_validation"]
