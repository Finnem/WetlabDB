"""Attachment-role helpers for scaffold replacement (Slice 5)."""

from __future__ import annotations

import math

from rdkit import Chem

PHENOL_CORE_SMARTS = "Oc1ccccc1"


def phenol_core_smarts() -> Chem.Mol:
    q = Chem.MolFromSmarts(PHENOL_CORE_SMARTS)
    if q is None:
        raise RuntimeError("invalid phenol core SMARTS")
    return q


def phenol_core_match(mol: Chem.Mol) -> tuple[int, ...]:
    query = phenol_core_smarts()
    matches = mol.GetSubstructMatches(query, uniquify=True)
    if not matches:
        return ()
    return max(matches, key=len)


def ring_atoms_from_phenol_match(mol: Chem.Mol, match: tuple[int, ...]) -> set[int]:
    return {idx for idx in match[1:]}


def phenol_oh_atom(match: tuple[int, ...]) -> int:
    return match[0]


def phenol_attachment_ring_atom(mol: Chem.Mol, match: tuple[int, ...]) -> int | None:
    """Ring atom bearing the largest exocyclic substituent other than OH (para bioisostere site)."""
    ring = ring_atoms_from_phenol_match(mol, match)
    oh = phenol_oh_atom(match)
    oh_ring = next(
        (n.GetIdx() for n in mol.GetAtomWithIdx(oh).GetNeighbors() if n.GetIdx() in ring),
        None,
    )
    if oh_ring is None:
        return None

    best: tuple[int, int, int] | None = None
    for ai in ring:
        if ai == oh_ring:
            continue
        exo = [
            n
            for n in mol.GetAtomWithIdx(ai).GetNeighbors()
            if n.GetIdx() not in ring and n.GetIdx() != oh
        ]
        if not exo:
            continue
        heavy = [n for n in exo if n.GetAtomicNum() > 1]
        if not heavy:
            continue
        score = (len(heavy), max(n.GetAtomicNum() for n in heavy), ai)
        if best is None or score > best:
            best = score
    return best[2] if best else None


def substituent_anchor_atom(mol: Chem.Mol, ring_atom: int, ring_atoms: set[int]) -> int | None:
    """First heavy atom exocyclic to ring_atom (attachment origin)."""
    exo = [
        n.GetIdx()
        for n in mol.GetAtomWithIdx(ring_atom).GetNeighbors()
        if n.GetIdx() not in ring_atoms and n.GetAtomicNum() > 1
    ]
    if not exo:
        return None
    return exo[0]


def attachment_vector(mol: Chem.Mol, ring_atom: int, anchor: int) -> tuple[float, float] | None:
    if mol.GetNumConformers() == 0:
        return None
    conf = mol.GetConformer()
    r = conf.GetAtomPosition(ring_atom)
    a = conf.GetAtomPosition(anchor)
    dx, dy = a.x - r.x, a.y - r.y
    norm = math.hypot(dx, dy)
    if norm < 1e-6:
        return None
    return (dx / norm, dy / norm)


def angle_degrees(v1: tuple[float, float], v2: tuple[float, float]) -> float:
    dot = max(-1.0, min(1.0, v1[0] * v2[0] + v1[1] * v2[1]))
    return math.degrees(math.acos(dot))


def is_phenol_bioisostere_case(comparison: dict) -> bool:
    retained = str(comparison.get("retained_fragment") or "").lower()
    roles = comparison.get("roles") or {}
    if "phenol" in retained:
        return True
    if "phenol_anchor" in roles and "bioisostere_attachment" in roles:
        return True
    return False


__all__ = [
    "PHENOL_CORE_SMARTS",
    "angle_degrees",
    "attachment_vector",
    "is_phenol_bioisostere_case",
    "phenol_attachment_ring_atom",
    "phenol_core_match",
    "phenol_core_smarts",
    "phenol_oh_atom",
    "ring_atoms_from_phenol_match",
    "substituent_anchor_atom",
]
