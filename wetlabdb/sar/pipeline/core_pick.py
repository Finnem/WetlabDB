"""Interactive core picking: subgraph SMARTS, heteroatom generalization, depict."""

from __future__ import annotations

import math
from typing import Any, Iterable, Literal, Sequence

from rdkit import Chem
from rdkit.Chem import AllChem, rdFMCS
from rdkit.Chem.Draw import rdMolDraw2D

from wetlabdb.chem.smiles import parse_smiles, parse_smarts, perceive_aromaticity

# C plus common ring heteroatoms — used when a core position is mixed C/hetero.
_RING_ANY_HETERO = frozenset({6, 7, 8, 15, 16})
_HETERO = frozenset({7, 8, 15, 16})
_MIN_CORE_ATOMS = 5
_GUESS_MCS_TIMEOUT = 4
CoreAtomMode = Literal["exact", "group", "hetero", "any"]
_VALID_CORE_ATOM_MODES = frozenset({"exact", "group", "hetero", "any"})
# ChemDraw ACS-1996 "margin width" 1.6 pt / "fixed length" 14.4 pt.
_ACS_MARGIN_OVER_BOND = 1.6 / 14.4


def normalize_core_atom_mode(raw: str | None) -> CoreAtomMode:
    value = str(raw or "exact").strip().lower()
    if value in _VALID_CORE_ATOM_MODES:
        return value  # type: ignore[return-value]
    return "exact"


def default_core_atom_mode(atom: Chem.Atom) -> CoreAtomMode:
    z = atom.GetAtomicNum()
    if atom.GetIsAromatic() and z in _HETERO:
        return "group"
    return "exact"


def allowed_z_for_atom_mode(z: int, aromatic: bool, mode: CoreAtomMode) -> set[int]:
    if mode == "any":
        return {0}
    if mode == "exact":
        return {z}
    if mode == "hetero":
        if aromatic:
            return set(_HETERO)
        return {z}
    if mode == "group":
        from wetlabdb.sar.pipeline.isomorphisms import periodic_group

        zs = set(periodic_group(z))
        if aromatic and z == 6:
            zs.add(7)
        return zs
    return {z}


def allowed_z_from_atom_modes(
    mol: Chem.Mol,
    core_atoms: Sequence[int],
    atom_modes: dict[int, str] | None,
) -> dict[int, set[int]]:
    modes = atom_modes or {}
    allowed: dict[int, set[int]] = {}
    for idx in core_atoms:
        if not 0 <= idx < mol.GetNumAtoms():
            continue
        atom = mol.GetAtomWithIdx(idx)
        mode = normalize_core_atom_mode(modes.get(idx))
        allowed[idx] = allowed_z_for_atom_mode(atom.GetAtomicNum(), atom.GetIsAromatic(), mode)
    return allowed


def atom_group_elements(z: int, aromatic: bool, mode: CoreAtomMode) -> list[str]:
    if mode == "any":
        return ["*"]
    pt = Chem.GetPeriodicTable()
    nums = allowed_z_for_atom_mode(z, aromatic, mode)
    if 0 in nums:
        return ["*"]
    return [pt.GetElementSymbol(n) for n in sorted(nums)]


_CORE_MODE_ORDER: tuple[CoreAtomMode, ...] = ("exact", "group", "hetero", "any")


def _query_display_label(atom: Chem.Atom, mode: CoreAtomMode) -> str:
    mode = normalize_core_atom_mode(mode)
    if mode == "exact":
        return atom.GetSymbol()
    if mode == "any":
        return "any"
    elems = atom_group_elements(atom.GetAtomicNum(), atom.GetIsAromatic(), mode)
    if len(elems) == 1:
        return elems[0]
    if len(elems) <= 4:
        return "/".join(elems)
    if mode == "hetero":
        return "Het"
    return "Grp"


def _minimum_mode_for_elements(ref_atom: Chem.Atom, analog_z: int) -> CoreAtomMode:
    ref_z = ref_atom.GetAtomicNum()
    arom = ref_atom.GetIsAromatic()
    for mode in _CORE_MODE_ORDER:
        allowed = allowed_z_for_atom_mode(ref_z, arom, mode)
        if ref_z in allowed and analog_z in allowed:
            return mode
    return "any"


def cycle_core_atom_mode(current: CoreAtomMode) -> CoreAtomMode | None:
    try:
        pos = _CORE_MODE_ORDER.index(current)
    except ValueError:
        return None
    if pos + 1 >= len(_CORE_MODE_ORDER):
        return None
    return _CORE_MODE_ORDER[pos + 1]


def generalize_core_from_analog(
    reference_smiles: str,
    core_atoms: Sequence[int],
    atom_modes: dict[int, str] | None,
    analog_smiles: str,
    analog_atom_idx: int,
    *,
    ignore_bond_order: bool = False,
) -> dict[str, Any]:
    """Map an analog atom click onto a reference core atom and widen its match mode."""
    ref = _mol(reference_smiles)
    analog = _mol(analog_smiles)
    empty = {
        "ok": False,
        "message": "Could not parse structure",
        "core_atoms": list(core_atoms),
        "atom_modes": {},
        "mapped_ref_atom": None,
    }
    if ref is None or analog is None:
        return empty
    core = [int(i) for i in core_atoms if 0 <= int(i) < ref.GetNumAtoms()]
    if not core:
        return {**empty, "message": "Select a core on the reference first"}
    if analog_atom_idx < 0 or analog_atom_idx >= analog.GetNumAtoms():
        return {**empty, "message": "Invalid atom"}

    modes = atom_modes_for_core(ref, core, atom_modes)
    smarts = smarts_from_core(ref, core, atom_modes=modes) or ""
    mapped = _map_analog_atom_to_ref(
        ref,
        core,
        analog,
        int(analog_atom_idx),
        smarts,
        ignore_bond_order=ignore_bond_order,
    )
    if mapped is None:
        return {
            **empty,
            "message": "Could not map that atom onto the core — try growing the core on the reference",
            "core_atoms": core,
            "atom_modes": {str(i): modes[i] for i in core},
        }

    if mapped not in core:
        if not any(ref.GetBondBetweenAtoms(mapped, c) is not None for c in core) and not connected_atom_set(
            ref, [*core, mapped]
        ):
            return {
                **empty,
                "message": "That atom is not part of the shared core",
                "core_atoms": core,
                "atom_modes": {str(i): modes[i] for i in core},
            }
        core.append(mapped)
        modes[mapped] = default_core_atom_mode(ref.GetAtomWithIdx(mapped))

    ref_atom = ref.GetAtomWithIdx(mapped)
    analog_z = analog.GetAtomWithIdx(int(analog_atom_idx)).GetAtomicNum()
    current = modes.get(mapped, "exact")
    allowed_now = allowed_z_for_atom_mode(
        ref_atom.GetAtomicNum(), ref_atom.GetIsAromatic(), current
    )
    if analog_z in allowed_now:
        next_mode = cycle_core_atom_mode(current)
        modes[mapped] = next_mode if next_mode else "any"
    else:
        modes[mapped] = _minimum_mode_for_elements(ref_atom, analog_z)

    return {
        "ok": True,
        "message": "",
        "core_atoms": core,
        "atom_modes": {str(i): modes[i] for i in core},
        "mapped_ref_atom": mapped,
    }


def atom_modes_for_core(
    mol: Chem.Mol,
    core_atoms: Sequence[int],
    atom_modes: dict[int, str] | None = None,
) -> dict[int, CoreAtomMode]:
    modes = atom_modes or {}
    out: dict[int, CoreAtomMode] = {}
    for idx in core_atoms:
        if not 0 <= idx < mol.GetNumAtoms():
            continue
        if idx in modes:
            out[idx] = normalize_core_atom_mode(modes[idx])
        else:
            out[idx] = default_core_atom_mode(mol.GetAtomWithIdx(idx))
    return out


def _mol(smiles: str) -> Chem.Mol | None:
    mol = parse_smiles(smiles)
    if mol is None:
        return None
    perceive_aromaticity(mol)
    return mol


def connected_atom_set(mol: Chem.Mol, atom_indices: Sequence[int]) -> bool:
    wanted = sorted(set(int(i) for i in atom_indices if 0 <= int(i) < mol.GetNumAtoms()))
    if len(wanted) <= 1:
        return True
    remaining = set(wanted)
    start = wanted[0]
    stack = [start]
    remaining.discard(start)
    while stack and remaining:
        current = stack.pop()
        for nbr in mol.GetAtomWithIdx(current).GetNeighbors():
            ni = nbr.GetIdx()
            if ni in remaining:
                remaining.discard(ni)
                stack.append(ni)
    return not remaining


def _order_ring(mol: Chem.Mol, ring: set[int], start: int) -> tuple[int, ...]:
    if start not in ring:
        return ()
    nbrs = [n.GetIdx() for n in mol.GetAtomWithIdx(start).GetNeighbors() if n.GetIdx() in ring]
    if not nbrs:
        return ()
    orders: list[tuple[int, ...]] = []
    for first in nbrs:
        order = [start, first]
        prev, current = start, first
        while len(order) < len(ring):
            nxt = [
                n.GetIdx()
                for n in mol.GetAtomWithIdx(current).GetNeighbors()
                if n.GetIdx() in ring and n.GetIdx() != prev
            ]
            if len(nxt) != 1:
                break
            prev, current = current, nxt[0]
            order.append(current)
        if len(order) == len(ring):
            orders.append(tuple(order))
    return orders[0] if orders else ()


def _reverse_ring(order: tuple[int, ...]) -> tuple[int, ...]:
    if not order:
        return ()
    return (order[0],) + tuple(reversed(order[1:]))


def _query_smarts_for(zs: set[int], aromatic: bool) -> str:
    nums = ",".join(f"#{z}" for z in sorted(zs))
    if aromatic:
        return f"[{nums};a]"
    return f"[{nums}]"


def _expand_for_hetero(zs: set[int], aromatic: bool) -> set[int]:
    """Widen only aromatic (ring) heteros. Aliphatic picks stay literal."""
    if not zs:
        return zs
    if zs <= {6}:
        return zs
    if aromatic and (zs & _HETERO):
        return set(_RING_ANY_HETERO)
    return zs


def _atom_from_query(
    zs: set[int],
    aromatic: bool,
    fallback_z: int,
    *,
    expand_legacy: bool = False,
) -> Chem.Atom:
    if 0 in zs:
        smarts = "[*;a]" if aromatic else "[*]"
        q = Chem.AtomFromSmarts(smarts)
        if q is not None:
            return q
    if expand_legacy:
        expanded = _expand_for_hetero(zs, aromatic) or {fallback_z}
    else:
        expanded = zs or {fallback_z}
    q = Chem.AtomFromSmarts(_query_smarts_for(expanded, aromatic))
    if q is not None:
        return q
    return Chem.Atom(fallback_z)


def _demote_dangling_aromaticity(mol: Chem.Mol) -> None:
    """Drop aromatic flags on atoms/bonds that are not in a ring here."""
    try:
        mol.UpdatePropertyCache(strict=False)
        Chem.GetSSSR(mol)
    except Exception:
        pass
    ring_atoms: set[int] = set()
    try:
        for ring in mol.GetRingInfo().AtomRings():
            ring_atoms.update(ring)
    except Exception:
        pass
    for atom in mol.GetAtoms():
        if atom.GetIsAromatic() and atom.GetIdx() not in ring_atoms:
            atom.SetIsAromatic(False)
    for bond in mol.GetBonds():
        a, b = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        if bond.GetIsAromatic() and (a not in ring_atoms or b not in ring_atoms):
            bond.SetIsAromatic(False)
            if bond.GetBondType() == Chem.BondType.AROMATIC:
                bond.SetBondType(Chem.BondType.SINGLE)


def smarts_from_core(
    mol: Chem.Mol,
    core_atoms: Sequence[int],
    allowed_z: dict[int, set[int]] | None = None,
    *,
    atom_modes: dict[int, str] | None = None,
) -> str | None:
    indices = [i for i in core_atoms if 0 <= i < mol.GetNumAtoms()]
    if not indices:
        return None
    if not connected_atom_set(mol, indices):
        return None
    if atom_modes is not None:
        allowed = allowed_z_from_atom_modes(mol, indices, atom_modes)
    else:
        allowed = dict(allowed_z or {})
    rw = Chem.RWMol()
    old_to_new: dict[int, int] = {}
    for idx in indices:
        atom = mol.GetAtomWithIdx(idx)
        zs = set(allowed.get(idx) or {atom.GetAtomicNum()})
        rw.AddAtom(_atom_from_query(zs, atom.GetIsAromatic(), atom.GetAtomicNum(), expand_legacy=False))
        old_to_new[idx] = len(old_to_new)
    for bond in mol.GetBonds():
        a, b = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        if a not in old_to_new or b not in old_to_new:
            continue
        rw.AddBond(old_to_new[a], old_to_new[b], bond.GetBondType())
        new_bond = rw.GetBondBetweenAtoms(old_to_new[a], old_to_new[b])
        if new_bond is not None:
            new_bond.SetIsAromatic(bond.GetIsAromatic())
    qmol = rw.GetMol()
    try:
        return Chem.MolToSmarts(qmol)
    except Exception:
        return None


def _query_atom_any_aromaticity(atom: Chem.Atom) -> Chem.Atom:
    """Keep element/query lists, drop aromaticity so ``c`` matches ``C``."""
    z = atom.GetAtomicNum()
    smarts = atom.GetSmarts() or ""
    if smarts.startswith("[") and ("," in smarts or "#" in smarts):
        inner = (
            smarts[1:-1]
            .replace(";a", "")
            .replace(";A", "")
            .replace("&a", "")
            .replace("&A", "")
        )
        query = Chem.AtomFromSmarts(f"[{inner}]")
        if query is not None:
            return query
    if z > 0:
        if "H" in smarts:
            cleaned = smarts.strip("[]")
            symbol = atom.GetSymbol()
            cleaned = cleaned.replace(symbol.lower(), f"#{z}").replace(symbol, f"#{z}")
            query = Chem.AtomFromSmarts(f"[{cleaned}]")
            if query is not None:
                return query
        query = Chem.AtomFromSmarts(f"[#{z}]")
        if query is not None:
            return query
    fallback = Chem.AtomFromSmarts("[*]")
    return fallback if fallback is not None else Chem.Atom(6)


def ignore_bond_order_query(query: Chem.Mol) -> Chem.Mol:
    """Match-only rewrite: unspecified bonds, element without aromaticity.

    Never use the result for depiction — SMARTS query bonds draw as unknown
    order (grey dashed). Stored core SMARTS and drawings stay on the source
    molecule's real bond orders.
    """
    rw = Chem.RWMol()
    for atom in query.GetAtoms():
        rw.AddAtom(_query_atom_any_aromaticity(atom))
    for bond in query.GetBonds():
        begin, end = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        rw.AddBond(begin, end, Chem.BondType.UNSPECIFIED)
        new_bond = rw.GetBondBetweenAtoms(begin, end)
        if new_bond is not None:
            new_bond.SetBondType(Chem.BondType.UNSPECIFIED)
            new_bond.SetIsAromatic(False)
    return rw.GetMol()


def _parse_match_query(smarts: str, ignore_bond_order: bool) -> Chem.Mol | None:
    query = parse_smarts(smarts)
    if query is None:
        return None
    if ignore_bond_order:
        return ignore_bond_order_query(query)
    return query


def match_atom_indices(
    mol: Chem.Mol,
    smarts: str,
    *,
    ignore_bond_order: bool = False,
) -> list[int]:
    query = _parse_match_query(smarts, ignore_bond_order)
    if query is None:
        return []
    match = mol.GetSubstructMatch(query)
    return list(match) if match else []


def _mapping_allowed_z(ref_mol: Chem.Mol, core_atoms: Sequence[int]) -> dict[int, set[int]]:
    """Loose element sets used only to correspond atoms across analogs."""
    allowed: dict[int, set[int]] = {}
    for idx in core_atoms:
        atom = ref_mol.GetAtomWithIdx(idx)
        if atom.GetIsAromatic():
            allowed[idx] = set(_RING_ANY_HETERO)
        else:
            z = atom.GetAtomicNum()
            allowed[idx] = {z} | _HETERO if z == 6 else {z, 6}
    return allowed


def _analog_to_core_map(
    ref_mol: Chem.Mol,
    core_atoms: Sequence[int],
    analog_mol: Chem.Mol,
    smarts: str,
    *,
    ignore_bond_order: bool = False,
) -> dict[int, int]:
    """Map analog atom index → reference atom index for the current core."""
    for candidate in (smarts, smarts_from_core(ref_mol, core_atoms, _mapping_allowed_z(ref_mol, core_atoms))):
        if not candidate:
            continue
        query = _parse_match_query(candidate, ignore_bond_order)
        if query is None:
            continue
        match = analog_mol.GetSubstructMatch(query)
        if match and len(match) == len(core_atoms):
            return {match[i]: core_atoms[i] for i in range(len(match))}
    return {}


def _map_analog_atom_to_ref(
    ref_mol: Chem.Mol,
    core_atoms: Sequence[int],
    analog_mol: Chem.Mol,
    analog_atom: int,
    smarts: str,
    *,
    ignore_bond_order: bool = False,
) -> int | None:
    """Map an analog atom onto a reference atom (core or ring-equivalent)."""
    if analog_atom < 0 or analog_atom >= analog_mol.GetNumAtoms():
        return None
    analog_to_core = _analog_to_core_map(
        ref_mol, core_atoms, analog_mol, smarts, ignore_bond_order=ignore_bond_order
    )
    if analog_atom in analog_to_core:
        return analog_to_core[analog_atom]

    analog_rings = [set(r) for r in analog_mol.GetRingInfo().AtomRings()]
    core_set = set(core_atoms)
    for ring in analog_rings:
        if analog_atom not in ring:
            continue
        seeds = [a for a in ring if a in analog_to_core]
        if not seeds:
            continue
        seed_a = seeds[0]
        seed_r = analog_to_core[seed_a]
        analog_order = _order_ring(analog_mol, ring, seed_a)
        if not analog_order:
            continue
        pos = analog_order.index(analog_atom)
        for ref_ring_t in ref_mol.GetRingInfo().AtomRings():
            ref_ring = set(ref_ring_t)
            if seed_r not in ref_ring:
                continue
            if len(ref_ring) != len(ring):
                continue
            ref_order = _order_ring(ref_mol, ref_ring, seed_r)
            if not ref_order:
                continue
            for order in (ref_order, _reverse_ring(ref_order)):
                if len(order) != len(analog_order):
                    continue
                cand = order[pos]
                if cand in core_set or cand in ref_ring:
                    return cand
    return None


def preview_core(
    reference_smiles: str,
    core_atoms: Sequence[int],
    molecules: list[dict[str, Any]],
    *,
    ignore_bond_order: bool = False,
    atom_modes: dict[int, str] | None = None,
    remap_smarts: str | None = None,
) -> dict[str, Any]:
    ref = _mol(reference_smiles)
    empty_matches = [
        {"id": m.get("id"), "matched": False, "atom_indices": []} for m in molecules
    ]
    if ref is None:
        return {
            "smarts": "",
            "core_atoms": [],
            "connected": False,
            "message": "Could not parse reference structure",
            "generalized_atoms": [],
            "atom_modes": {},
            "matches": empty_matches,
        }

    core = [int(i) for i in core_atoms if 0 <= int(i) < ref.GetNumAtoms()]
    modes_in: dict[int, str] = {}
    for key, value in (atom_modes or {}).items():
        try:
            modes_in[int(key)] = str(value)
        except (TypeError, ValueError):
            continue
    if remap_smarts and str(remap_smarts).strip():
        hit = match_atom_indices(ref, str(remap_smarts).strip(), ignore_bond_order=ignore_bond_order)
        if hit:
            core = hit
            modes_in = atom_modes_for_core(ref, core, modes_in)

    if not core:
        return {
            "smarts": "",
            "core_atoms": [],
            "connected": True,
            "message": "Click atoms on the reference structure to define the core",
            "generalized_atoms": [],
            "atom_modes": {},
            "matches": empty_matches,
        }
    if not connected_atom_set(ref, core):
        return {
            "smarts": "",
            "core_atoms": core,
            "connected": False,
            "message": "Core atoms must form one connected piece — click atoms next to the current selection",
            "generalized_atoms": [],
            "atom_modes": {str(i): modes_in[i] for i in core if i in modes_in},
            "matches": [],
        }

    resolved_modes = atom_modes_for_core(ref, core, modes_in)
    smarts = smarts_from_core(ref, core, atom_modes=resolved_modes) or ""
    generalized = [i for i in core if resolved_modes.get(i, "exact") != "exact"]
    matches = []
    for spec in molecules:
        mid = spec.get("id")
        analog = _mol(str(spec.get("smiles") or ""))
        if analog is None or not smarts:
            matches.append({"id": mid, "matched": False, "atom_indices": []})
            continue
        hit = match_atom_indices(analog, smarts, ignore_bond_order=ignore_bond_order)
        matches.append({"id": mid, "matched": bool(hit), "atom_indices": hit})

    n_wild = len(generalized)
    message = f"{len(core)}-atom core · match as written in SMARTS"
    if n_wild:
        message += f" · {n_wild} generalized position" + ("s" if n_wild != 1 else "")
    unmatched = sum(1 for m in matches if not m["matched"])
    if unmatched:
        message += f" · {unmatched} structure" + ("s" if unmatched != 1 else "") + " unmatched"
    return {
        "smarts": smarts,
        "core_atoms": core,
        "connected": True,
        "message": message,
        "generalized_atoms": generalized,
        "atom_modes": {str(i): resolved_modes[i] for i in core},
        "matches": matches,
    }


def extract_atom_subset(mol: Chem.Mol, atom_indices: Sequence[int]) -> Chem.Mol | None:
    """Induced subgraph as a concrete molecule (real atoms and bond orders)."""
    keep = [int(i) for i in atom_indices if 0 <= int(i) < mol.GetNumAtoms()]
    if not keep:
        return None
    keep_set = set(keep)
    rw = Chem.RWMol()
    old_to_new: dict[int, int] = {}
    for old_idx in keep:
        src = mol.GetAtomWithIdx(old_idx)
        atom = Chem.Atom(src.GetAtomicNum() or 6)
        atom.SetFormalCharge(src.GetFormalCharge())
        atom.SetNumExplicitHs(src.GetNumExplicitHs())
        atom.SetNoImplicit(src.GetNoImplicit())
        atom.SetIsAromatic(src.GetIsAromatic())
        old_to_new[old_idx] = rw.AddAtom(atom)
    for bond in mol.GetBonds():
        a1, a2 = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        if a1 not in keep_set or a2 not in keep_set:
            continue
        bt = bond.GetBondType()
        if bt == Chem.BondType.UNSPECIFIED:
            bt = Chem.BondType.AROMATIC if bond.GetIsAromatic() else Chem.BondType.SINGLE
        rw.AddBond(old_to_new[a1], old_to_new[a2], bt)
        new_bond = rw.GetBondBetweenAtoms(old_to_new[a1], old_to_new[a2])
        if new_bond is not None:
            new_bond.SetIsAromatic(bond.GetIsAromatic())
    out = rw.GetMol()
    try:
        Chem.SanitizeMol(out)
    except Exception:
        _demote_dangling_aromaticity(out)
        try:
            Chem.SanitizeMol(out)
        except Exception:
            pass
    if mol.GetNumConformers():
        src_conf = mol.GetConformer()
        conf = Chem.Conformer(out.GetNumAtoms())
        for old_idx, new_idx in old_to_new.items():
            conf.SetAtomPosition(new_idx, src_conf.GetAtomPosition(old_idx))
        out.RemoveAllConformers()
        out.AddConformer(conf, assignId=True)
    elif out.GetNumConformers() == 0:
        try:
            AllChem.Compute2DCoords(out)
        except Exception:
            return None
    return out


def _largest_ring_system(mol: Chem.Mol) -> list[int]:
    try:
        mol.UpdatePropertyCache(strict=False)
        Chem.GetSSSR(mol)
    except Exception:
        pass
    rings = mol.GetRingInfo().AtomRings()
    if not rings:
        return []
    keep = set(max(rings, key=len))
    grew = True
    while grew:
        grew = False
        for ring in rings:
            atoms = set(ring)
            if keep & atoms and not atoms <= keep:
                keep |= atoms
                grew = True
    return sorted(keep)


def _conservative_core_atoms(mol: Chem.Mol, match: Sequence[int]) -> list[int]:
    matched = [int(i) for i in match if 0 <= int(i) < mol.GetNumAtoms()]
    if len(matched) < _MIN_CORE_ATOMS:
        return []
    ring_atoms = [i for i in matched if mol.GetAtomWithIdx(i).IsInRing()]
    if len(ring_atoms) >= _MIN_CORE_ATOMS and connected_atom_set(mol, ring_atoms):
        keep = set(ring_atoms)
        changed = True
        while changed:
            changed = False
            for idx in matched:
                if idx in keep:
                    continue
                nbrs = [
                    n.GetIdx()
                    for n in mol.GetAtomWithIdx(idx).GetNeighbors()
                    if n.GetIdx() in keep
                ]
                if len(nbrs) >= 2:
                    keep.add(idx)
                    changed = True
        ordered = [i for i in matched if i in keep]
        if len(ordered) >= _MIN_CORE_ATOMS and connected_atom_set(mol, ordered):
            return ordered
        return ring_atoms
    if connected_atom_set(mol, matched):
        return matched
    return []


def guess_shared_core(
    molecules: list[dict[str, Any]],
    reference_id: str | None = None,
    *,
    ignore_bond_order: bool = False,
) -> dict[str, Any]:
    """Guess a conservative shared scaffold: rings first, drop shared substituents."""
    empty = {
        "smarts": "",
        "source_id": reference_id or "",
        "core_atoms": [],
        "atom_modes": {},
        "message": "No conservative shared scaffold found",
    }
    parsed: list[tuple[str, Chem.Mol]] = []
    for spec in molecules:
        mid = str(spec.get("id") or "")
        mol = _mol(str(spec.get("smiles") or ""))
        if not mid or mol is None:
            continue
        parsed.append((mid, mol))
    if not parsed:
        return empty
    ids = [item[0] for item in parsed]
    source_id = reference_id if reference_id in ids else ids[0]
    by_id = dict(parsed)
    source = by_id[source_id]
    mols = [source] + [mol for mid, mol in parsed if mid != source_id]

    if len(parsed) == 1:
        atoms = _largest_ring_system(source)
        smarts = smarts_from_core(source, atoms) if atoms else ""
        if not smarts:
            return {**empty, "source_id": source_id}
        return {
            "smarts": smarts,
            "source_id": source_id,
            "core_atoms": atoms,
            "atom_modes": {str(i): "exact" for i in atoms},
            "message": f"Guessed {len(atoms)}-atom ring system",
        }

    modes = (
        (rdFMCS.AtomCompare.CompareElements, True),
        (rdFMCS.AtomCompare.CompareAnyHeavyAtom, True),
        (rdFMCS.AtomCompare.CompareElements, False),
    )
    bond_compare = (
        rdFMCS.BondCompare.CompareAny if ignore_bond_order else rdFMCS.BondCompare.CompareOrder
    )
    for atom_compare, complete_rings in modes:
        result = rdFMCS.FindMCS(
            mols,
            completeRingsOnly=complete_rings,
            atomCompare=atom_compare,
            bondCompare=bond_compare,
            ringMatchesRingOnly=True,
            timeout=_GUESS_MCS_TIMEOUT,
        )
        if result.canceled or not result.smartsString:
            continue
        query = Chem.MolFromSmarts(result.smartsString)
        if query is None:
            continue
        if ignore_bond_order:
            query = ignore_bond_order_query(query)
        if any(not mol.HasSubstructMatch(query) for mol in mols):
            continue
        match = source.GetSubstructMatch(query)
        atoms = _conservative_core_atoms(source, match)
        smarts = smarts_from_core(source, atoms) if atoms else ""
        if not smarts:
            continue
        return {
            "smarts": smarts,
            "source_id": source_id,
            "core_atoms": atoms,
            "atom_modes": {str(i): "exact" for i in atoms},
            "message": f"Guessed {len(atoms)}-atom shared scaffold",
        }
    return {**empty, "source_id": source_id}


def _parse_pose_molblock(text: str) -> Chem.Mol | None:
    """Parse a 2D molblock without eating the empty name line.

    RDKit writes ``\\n     RDKit          2D\\n\\n  counts...``. ``str.strip()``
    removes that leading newline, so line 4 becomes an atom record and
    ``MolFromMolBlock`` fails. The bake then falls back to a fresh SMILES
    layout — a different pose than the CSS-rotated drawing.
    """
    if not text or not str(text).strip():
        return None
    raw = str(text).replace("\r\n", "\n")
    candidates = [raw]
    stripped = raw.strip("\n")
    if not raw.startswith("\n"):
        candidates.append("\n" + stripped)
    for block in candidates:
        try:
            mol = Chem.MolFromMolBlock(block, sanitize=True, removeHs=False)
        except Exception:
            mol = None
        if mol is not None and mol.GetNumConformers() > 0:
            return mol
    return None


def _rotate_conformer_clockwise(mol: Chem.Mol, degrees: float) -> None:
    if mol.GetNumConformers() == 0:
        AllChem.Compute2DCoords(mol)
    theta = math.radians(float(degrees))
    cos_a, sin_a = math.cos(theta), math.sin(theta)
    conf = mol.GetConformer()
    count = mol.GetNumAtoms()
    if count == 0:
        return
    cx = sum(conf.GetAtomPosition(i).x for i in range(count)) / count
    cy = sum(conf.GetAtomPosition(i).y for i in range(count)) / count
    for i in range(count):
        point = conf.GetAtomPosition(i)
        x, y = point.x - cx, point.y - cy
        conf.SetAtomPosition(i, (cx + x * cos_a + y * sin_a, cy - x * sin_a + y * cos_a, 0.0))


def rotate_poses(molecules: list[dict[str, Any]], degrees: float) -> list[dict[str, str]]:
    """Rotate 2D poses clockwise (CSS-positive) and return molblocks."""
    poses: list[dict[str, str]] = []
    if abs(float(degrees)) < 1e-9:
        for spec in molecules:
            mid = str(spec.get("id") or "")
            block = str(spec.get("molblock") or "")
            if block.strip():
                poses.append({"id": mid, "molblock": block})
        return poses
    for spec in molecules:
        mid = str(spec.get("id") or "")
        mol = _parse_pose_molblock(str(spec.get("molblock") or ""))
        if mol is None:
            mol = _mol(str(spec.get("smiles") or ""))
        if mol is None or not mid:
            continue
        perceive_aromaticity(mol)
        _rotate_conformer_clockwise(mol, degrees)
        poses.append({"id": mid, "molblock": Chem.MolToMolBlock(mol, kekulize=False)})
    return poses


def _structure_drawer(mol: Chem.Mol) -> rdMolDraw2D.MolDraw2DSVG:
    """ACS 1996 flexi-canvas: 0.6 pt bonds, 10 pt labels, 14.4 pt mean bond.

    Uses ChemDraw's ACS margin (1.6 pt) so N⁺/O⁻ labels do not swallow bonds.
    ``prepareMolsBeforeDrawing`` stays on so aromatics kekulize — never draw
    SMARTS query/unspecified bonds as the structure.
    """
    drawer = rdMolDraw2D.MolDraw2DSVG(-1, -1)
    mean = float(rdMolDraw2D.MeanBondLength(mol) or 1.5)
    if mean <= 0:
        mean = 1.5
    opts = drawer.drawOptions()
    rdMolDraw2D.SetACS1996Mode(opts, mean)
    opts.additionalAtomLabelPadding = _ACS_MARGIN_OVER_BOND
    opts.prepareMolsBeforeDrawing = True
    drawer.DrawMolecule(mol)
    return drawer


def depict_structure(
    smiles: str,
    *,
    width: int = 280,
    height: int = 200,
    highlight: Iterable[int] | None = None,
    selected: Iterable[int] | None = None,
    fragment_atoms: Sequence[int] | None = None,
    molblock: str | None = None,
    core_atom_modes: dict[int, str] | None = None,
    query_labels: bool = False,
) -> dict[str, Any] | None:
    del width, height
    mol = _parse_pose_molblock(str(molblock or ""))
    if mol is None:
        mol = _mol(smiles)
        if mol is None:
            return None
    else:
        perceive_aromaticity(mol)
    if any(bond.GetBondType() == Chem.BondType.UNSPECIFIED for bond in mol.GetBonds()):
        return None
    parent = Chem.Mol(mol)
    fragment_keep: list[int] = []
    if fragment_atoms:
        fragment_keep = [int(i) for i in fragment_atoms if 0 <= int(i) < mol.GetNumAtoms()]
        mol = extract_atom_subset(mol, fragment_keep)
        if mol is None:
            return None
        if any(bond.GetBondType() == Chem.BondType.UNSPECIFIED for bond in mol.GetBonds()):
            return None
    if mol.GetNumConformers() == 0:
        try:
            AllChem.Compute2DCoords(mol)
        except Exception:
            return None
    highlight_set = {int(i) for i in (highlight or []) if 0 <= int(i) < mol.GetNumAtoms()}
    selected_set = {int(i) for i in (selected or []) if 0 <= int(i) < mol.GetNumAtoms()}
    try:
        drawer = _structure_drawer(mol)
        drawer.FinishDrawing()
        svg = drawer.GetDrawingText()
        canvas_w = int(drawer.Width()) or 1
        canvas_h = int(drawer.Height()) or 1
        atoms = []
        mode_by_ref: dict[int, str] = {}
        if core_atom_modes:
            for key, value in core_atom_modes.items():
                try:
                    mode_by_ref[int(key)] = str(value)
                except (TypeError, ValueError):
                    continue
        for idx in range(mol.GetNumAtoms()):
            pt = drawer.GetDrawCoords(idx)
            atom = mol.GetAtomWithIdx(idx)
            ref_idx = fragment_keep[idx] if fragment_keep and idx < len(fragment_keep) else idx
            src_atom = parent.GetAtomWithIdx(ref_idx) if 0 <= ref_idx < parent.GetNumAtoms() else atom
            mode = normalize_core_atom_mode(mode_by_ref.get(ref_idx))
            query_label = ""
            if ref_idx in mode_by_ref:
                query_label = _query_display_label(src_atom, mode)
            atoms.append(
                {
                    "idx": idx,
                    "x": float(pt.x),
                    "y": float(pt.y),
                    "symbol": atom.GetSymbol(),
                    "atomic_num": atom.GetAtomicNum(),
                    "charge": int(atom.GetFormalCharge()),
                    "aromatic": bool(atom.GetIsAromatic()),
                    "selected": idx in selected_set,
                    "matched": idx in highlight_set,
                    "neighbors": [n.GetIdx() for n in atom.GetNeighbors()],
                    "query_label": query_label,
                }
            )
        return {"svg": svg, "width": canvas_w, "height": canvas_h, "atoms": atoms}
    except Exception:
        return None


__all__ = [
    "CoreAtomMode",
    "allowed_z_for_atom_mode",
    "allowed_z_from_atom_modes",
    "atom_group_elements",
    "atom_modes_for_core",
    "cycle_core_atom_mode",
    "connected_atom_set",
    "default_core_atom_mode",
    "depict_structure",
    "extract_atom_subset",
    "generalize_core_from_analog",
    "guess_shared_core",
    "ignore_bond_order_query",
    "match_atom_indices",
    "normalize_core_atom_mode",
    "preview_core",
    "rotate_poses",
    "smarts_from_core",
]
