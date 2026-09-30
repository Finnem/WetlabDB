"""Six-membered aromatic ring helpers for atom-tolerant alignment."""

from __future__ import annotations

from rdkit import Chem


def six_membered_aromatic_rings(mol: Chem.Mol) -> list[tuple[int, ...]]:
    rings: list[tuple[int, ...]] = []
    ri = mol.GetRingInfo()
    for ring in ri.AtomRings():
        if len(ring) != 6:
            continue
        if all(mol.GetAtomWithIdx(i).GetIsAromatic() for i in ring):
            rings.append(tuple(ring))
    return rings


def _walk_ring(
    mol: Chem.Mol,
    ring_atoms: set[int],
    start: int,
    *,
    first_step: int | None = None,
) -> tuple[int, ...]:
    order = [start]
    prev: int | None = None
    current = start
    if first_step is not None:
        if first_step not in ring_atoms or first_step == start:
            return ()
        order.append(first_step)
        prev, current = start, first_step
    while len(order) < len(ring_atoms):
        nbrs = [
            n.GetIdx()
            for n in mol.GetAtomWithIdx(current).GetNeighbors()
            if n.GetIdx() in ring_atoms and n.GetIdx() != prev
        ]
        if len(nbrs) != 1:
            break
        prev, current = current, nbrs[0]
        order.append(current)
    return tuple(order) if len(order) == len(ring_atoms) else ()


# Ring role convention from M02: amino at position 1 (index 0), chloro at position 4 (index 3).
CHLORO_RING_INDEX = 3


def order_ring_atoms(
    mol: Chem.Mol,
    ring_atoms: set[int],
    start: int,
    *,
    marker_end: int | None = None,
    marker_index: int = CHLORO_RING_INDEX,
) -> tuple[int, ...]:
    if start not in ring_atoms:
        return ()
    first_candidates = [
        n.GetIdx()
        for n in mol.GetAtomWithIdx(start).GetNeighbors()
        if n.GetIdx() in ring_atoms
    ]
    if not first_candidates:
        return ()
    if len(first_candidates) == 1:
        return _walk_ring(mol, ring_atoms, start, first_step=first_candidates[0])

    orders: list[tuple[int, ...]] = []
    for step in first_candidates:
        walked = _walk_ring(mol, ring_atoms, start, first_step=step)
        if walked:
            orders.append(walked)
    if not orders:
        return ()
    if marker_end is None or marker_end not in ring_atoms:
        return orders[0]
    return min(
        orders,
        key=lambda o: abs(o.index(marker_end) - marker_index) if marker_end in o else 999,
    )


def _is_exocyclic(mol: Chem.Mol, ring_atoms: set[int], atom_idx: int, neighbor_idx: int) -> bool:
    return neighbor_idx not in ring_atoms


def ring_attachment_roles(mol: Chem.Mol, ring_atoms: set[int]) -> dict[str, int | None]:
    """Detect amino (primary) and chloro attachment ring atoms."""
    amino_site: int | None = None
    chloro_site: int | None = None
    for ai in ring_atoms:
        atom = mol.GetAtomWithIdx(ai)
        for nbr in atom.GetNeighbors():
            ni = nbr.GetIdx()
            if not _is_exocyclic(mol, ring_atoms, ai, ni):
                continue
            z = nbr.GetAtomicNum()
            if z == 17:
                chloro_site = ai
            if z == 7:
                amino_site = ai
    return {"amino_site": amino_site, "chloro_site": chloro_site}


def pick_reference_ring(mol: Chem.Mol) -> tuple[tuple[int, ...], dict[str, int | None]] | None:
    for ring in six_membered_aromatic_rings(mol):
        ring_set = set(ring)
        roles = ring_attachment_roles(mol, ring_set)
        if roles["amino_site"] is None or roles["chloro_site"] is None:
            continue
        order = order_ring_atoms(mol, ring_set, roles["amino_site"], marker_end=roles["chloro_site"])  # type: ignore[arg-type]
        if len(order) == 6:
            return order, roles
    return None


def allowed_cn_swap_at(ref_mol: Chem.Mol, ref_idx: int, roles: dict[str, int | None]) -> bool:
    if ref_idx in (roles.get("amino_site"), roles.get("chloro_site")):
        return False
    z = ref_mol.GetAtomWithIdx(ref_idx).GetAtomicNum()
    return z in (6, 7)


def elements_compatible(
    ref_mol: Chem.Mol,
    ref_idx: int,
    tgt_mol: Chem.Mol,
    tgt_idx: int,
    roles: dict[str, int | None],
    *,
    allow_cn: bool,
) -> bool:
    rz = ref_mol.GetAtomWithIdx(ref_idx).GetAtomicNum()
    tz = tgt_mol.GetAtomWithIdx(tgt_idx).GetAtomicNum()
    if rz == tz:
        return True
    if allow_cn and allowed_cn_swap_at(ref_mol, ref_idx, roles) and {rz, tz} == {6, 7}:
        return True
    return False


def role_positions_match(
    ref_order: tuple[int, ...],
    ref_roles: dict[str, int | None],
    tgt_order: tuple[int, ...],
    tgt_roles: dict[str, int | None],
) -> bool:
    ref_ai = ref_order.index(ref_roles["amino_site"])  # type: ignore[arg-type]
    ref_ci = ref_order.index(ref_roles["chloro_site"])  # type: ignore[arg-type]
    tgt_ai = tgt_order.index(tgt_roles["amino_site"])  # type: ignore[arg-type]
    tgt_ci = tgt_order.index(tgt_roles["chloro_site"])  # type: ignore[arg-type]
    return ref_ai == tgt_ai and ref_ci == tgt_ci


def exocyclic_pairs(
    ref_mol: Chem.Mol,
    ref_ring_atom: int,
    tgt_mol: Chem.Mol,
    tgt_ring_atom: int,
    ref_ring: set[int],
    tgt_ring: set[int],
) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = [(ref_ring_atom, tgt_ring_atom)]
    ref_side = [
        n.GetIdx()
        for n in ref_mol.GetAtomWithIdx(ref_ring_atom).GetNeighbors()
        if n.GetIdx() not in ref_ring
    ]
    tgt_side = [
        n.GetIdx()
        for n in tgt_mol.GetAtomWithIdx(tgt_ring_atom).GetNeighbors()
        if n.GetIdx() not in tgt_ring
    ]
    for ri in ref_side:
        rz = ref_mol.GetAtomWithIdx(ri).GetAtomicNum()
        for ti in tgt_side:
            tz = tgt_mol.GetAtomWithIdx(ti).GetAtomicNum()
            if rz == tz:
                pairs.append((ri, ti))
                break
    return pairs


__all__ = [
    "CHLORO_RING_INDEX",
    "elements_compatible",
    "exocyclic_pairs",
    "order_ring_atoms",
    "pick_reference_ring",
    "ring_attachment_roles",
    "role_positions_match",
    "six_membered_aromatic_rings",
]
