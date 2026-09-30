"""Scaffold isomorphisms, substituent roles, and global CP-SAT selection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

from rdkit import Chem

from wetlabdb.sar.hardening.limits import MAX_ENUMERATED_SOLUTIONS_DEFAULT, MAX_OPTIMIZER_TIME_SECONDS
from wetlabdb.sar.pipeline.core_pick import _parse_match_query

ScaffoldElementMode = Literal["element_agnostic", "from_smarts"]

# IUPAC-style groups for medicinal chemistry (atomic numbers).
_PERIODIC_GROUPS: tuple[frozenset[int], ...] = (
    frozenset({1}),  # H
    frozenset({6, 14}),  # C, Si
    frozenset({7, 15, 33}),  # N, P, As
    frozenset({8, 16, 34}),  # O, S, Se
    frozenset({9, 17, 35, 53}),  # F, Cl, Br, I
)

_Z_TO_GROUP: dict[int, int] = {}
for gi, members in enumerate(_PERIODIC_GROUPS):
    for z in members:
        _Z_TO_GROUP[z] = gi

_HEAVY_MIN = 2


def normalize_scaffold_element_mode(raw: str | None) -> ScaffoldElementMode:
    value = str(raw or "from_smarts").strip().lower()
    if value in ("element_agnostic", "ignore_elements"):
        return "element_agnostic"
    return "from_smarts"


def periodic_group(z: int) -> frozenset[int]:
    gi = _Z_TO_GROUP.get(z)
    if gi is None:
        return frozenset({z})
    return _PERIODIC_GROUPS[gi]


def _same_group(z_a: int, z_b: int) -> bool:
    ga = _Z_TO_GROUP.get(z_a)
    gb = _Z_TO_GROUP.get(z_b)
    if ga is None or gb is None:
        return z_a == z_b
    return ga == gb


def element_agnostic_query(query: Chem.Mol) -> Chem.Mol:
    """Same core topology as ``query``, every atom matches any heavy atom."""
    rw = Chem.RWMol()
    for _atom in query.GetAtoms():
        qatom = Chem.AtomFromSmarts("[*]")
        rw.AddAtom(qatom if qatom is not None else Chem.Atom(0))
    for bond in query.GetBonds():
        begin, end = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        rw.AddBond(begin, end, bond.GetBondType())
        new_bond = rw.GetBondBetweenAtoms(begin, end)
        if new_bond is not None:
            new_bond.SetIsAromatic(bond.GetIsAromatic())
            new_bond.SetBondType(bond.GetBondType())
    return rw.GetMol()


def match_query_from_smarts(
    core_smarts: str,
    *,
    mode: ScaffoldElementMode,
    ignore_bond_order: bool,
) -> Chem.Mol | None:
    """Build the match query from visible SMARTS (or element-agnostic topology)."""
    query = _parse_match_query(core_smarts, ignore_bond_order)
    if query is None:
        return None
    if mode == "element_agnostic":
        return element_agnostic_query(query)
    return query


@dataclass(frozen=True)
class SubstituentRole:
    key: str
    heavy_atoms: int


@dataclass
class IsomorphismCandidate:
    match: tuple[int, ...]
    substituents: tuple[SubstituentRole, ...]
    exact_element_matches: int = 0
    group_element_matches: int = 0
    signature: tuple[Any, ...] = field(default_factory=tuple)


def _heavy_count(mol: Chem.Mol) -> int:
    return sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() >= _HEAVY_MIN)


def _extract_side_chain(mol: Chem.Mol, root: int, core_atoms: set[int]) -> Chem.Mol | None:
    visited: set[int] = {root}
    stack = [root]
    while stack:
        cur = stack.pop()
        for nbr in mol.GetAtomWithIdx(cur).GetNeighbors():
            ni = nbr.GetIdx()
            if ni in core_atoms or ni in visited:
                continue
            visited.add(ni)
            stack.append(ni)
    if len(visited) == 1:
        atom = mol.GetAtomWithIdx(root)
        rw = Chem.RWMol()
        dummy = Chem.Atom(0)
        rw.AddAtom(dummy)
        ha = Chem.Atom(atom.GetAtomicNum())
        ha.SetFormalCharge(atom.GetFormalCharge())
        rw.AddAtom(ha)
        rw.AddBond(0, 1, Chem.BondType.SINGLE)
        return rw.GetMol()
    bonds: list[int] = []
    for b in mol.GetBonds():
        u, v = b.GetBeginAtomIdx(), b.GetEndAtomIdx()
        if u in visited and v in visited:
            bonds.append(b.GetIdx())
    try:
        frag = Chem.PathToSubmol(mol, bonds)
    except Exception:
        return None
    if frag is None:
        return None
    rw = Chem.RWMol(frag)
    dummy = Chem.Atom(0)
    rw.AddAtom(dummy)
    rw.AddBond(rw.GetNumAtoms() - 2, rw.GetNumAtoms() - 1, Chem.BondType.SINGLE)
    return rw.GetMol()


def _is_fused_neighbor(mol: Chem.Mol, site: int, neighbor: int, core_atoms: set[int]) -> bool:
    """True when neighbor is in a ring fused to the core (not a pendant substituent)."""
    for ring in mol.GetRingInfo().AtomRings():
        atoms = set(ring)
        if neighbor in atoms and site in atoms and (atoms & core_atoms) - {site}:
            return True
    return False


def _class_key(key: str) -> str:
    """Coarse group identity so methyl vs ethyl ester still count as the same side-chain class."""
    if not key:
        return ""
    return "|".join(_one_class(part) for part in key.split("|"))


def _one_class(key: str) -> str:
    if key in ("*F", "*Cl", "*Br", "*I"):
        return "halogen"
    if key in ("*N", "*N"):
        return "amino"
    if "C=O" in key and ("OC=O" in key or "COC=O" in key or "CCOC=O" in key or "C(=O)O" in key):
        return "ester"
    if key.startswith("*N") and "C=O" in key:
        return "amide"
    return key


def _substituent_at_site(
    mol: Chem.Mol,
    site_atom: int,
    core_atoms: set[int],
) -> SubstituentRole:
    exo: list[int] = []
    for nbr in mol.GetAtomWithIdx(site_atom).GetNeighbors():
        ni = nbr.GetIdx()
        if ni not in core_atoms and not _is_fused_neighbor(mol, site_atom, ni, core_atoms):
            exo.append(ni)
    if not exo:
        return SubstituentRole(key="", heavy_atoms=0)

    parts: list[str] = []
    total_heavy = 0
    for root in exo:
        frag = _extract_side_chain(mol, root, core_atoms)
        if frag is None:
            continue
        try:
            smi = Chem.MolToSmiles(frag, canonical=True)
        except Exception:
            continue
        parts.append(smi)
        total_heavy += _heavy_count(frag)
    if not parts:
        return SubstituentRole(key="", heavy_atoms=0)
    return SubstituentRole(key="|".join(sorted(parts)), heavy_atoms=total_heavy)


def _substituents_for_match(mol: Chem.Mol, match: Sequence[int]) -> tuple[SubstituentRole, ...]:
    core_atoms = set(match)
    return tuple(_substituent_at_site(mol, match[qi], core_atoms) for qi in range(len(match)))


def _element_overlay_counts(
    mol: Chem.Mol,
    match: Sequence[int],
    ref_mol: Chem.Mol,
    ref_match: Sequence[int],
) -> tuple[int, int]:
    if len(match) != len(ref_match):
        return 0, 0
    exact = 0
    group_only = 0
    for qi in range(len(match)):
        z = mol.GetAtomWithIdx(match[qi]).GetAtomicNum()
        rz = ref_mol.GetAtomWithIdx(ref_match[qi]).GetAtomicNum()
        if z == rz:
            exact += 1
        elif _same_group(z, rz):
            group_only += 1
    return exact, group_only


def enumerate_isomorphism_candidates(
    mol: Chem.Mol,
    query: Chem.Mol,
    ref_mol: Chem.Mol,
    ref_match: Sequence[int],
    *,
    mode: ScaffoldElementMode,
    max_matches: int = MAX_ENUMERATED_SOLUTIONS_DEFAULT,
) -> list[IsomorphismCandidate]:
    raw = mol.GetSubstructMatches(query, uniquify=False)
    if not raw:
        return []
    seen: set[tuple[Any, ...]] = set()
    out: list[IsomorphismCandidate] = []
    for match in raw:
        if len(out) >= max_matches:
            break
        m = tuple(match)
        subs = _substituents_for_match(mol, m)
        place = tuple(s.key for s in subs)
        if mode == "from_smarts":
            sig: tuple[Any, ...] = place + tuple(mol.GetAtomWithIdx(i).GetAtomicNum() for i in m)
        else:
            sig = place
        if sig in seen:
            continue
        seen.add(sig)
        exact, group_only = _element_overlay_counts(mol, m, ref_mol, ref_match)
        out.append(
            IsomorphismCandidate(
                match=m,
                substituents=subs,
                exact_element_matches=exact,
                group_element_matches=group_only,
                signature=sig,
            )
        )
    return out


def _pair_and_literal(model: Any, lit_a: Any, lit_b: Any) -> Any:
    z = model.NewBoolVar("agree")
    model.Add(z <= lit_a)
    model.Add(z <= lit_b)
    model.Add(z >= lit_a + lit_b - 1)
    return z


def _site_agreement(
    ca: IsomorphismCandidate,
    cb: IsomorphismCandidate,
    *,
    coarse: bool,
) -> int:
    n = min(len(ca.substituents), len(cb.substituents))
    total = 0
    for s in range(n):
        ra, rb = ca.substituents[s], cb.substituents[s]
        if not ra.key or not rb.key:
            continue
        if coarse:
            if _class_key(ra.key) != _class_key(rb.key):
                continue
        elif ra.key != rb.key:
            continue
        total += max(ra.heavy_atoms, rb.heavy_atoms, 1) ** 2
    return total


def _ref_anchor(cand: IsomorphismCandidate, ref_roles: tuple[SubstituentRole, ...], *, coarse: bool) -> int:
    total = 0
    for s, r in enumerate(ref_roles):
        if s >= len(cand.substituents) or not r.key:
            continue
        c = cand.substituents[s]
        if not c.key:
            continue
        if coarse:
            if _class_key(r.key) != _class_key(c.key):
                continue
        elif r.key != c.key:
            continue
        total += max(r.heavy_atoms, 1)
    return total


def _solve_with_cpsat(
    molecule_ids: list[str],
    candidates: dict[str, list[IsomorphismCandidate]],
    ref_roles: tuple[SubstituentRole, ...],
    *,
    ref_id: str,
    ref_pin: int,
    mode: ScaffoldElementMode,
) -> dict[str, IsomorphismCandidate] | None:
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        return _solve_greedy(
            molecule_ids, candidates, ref_roles, ref_id=ref_id, ref_pin=ref_pin, mode=mode
        )

    def add_vars_and_constraints(model: Any) -> dict[tuple[str, int], Any]:
        x: dict[tuple[str, int], Any] = {}
        for mid in molecule_ids:
            cands = candidates[mid]
            for ki in range(len(cands)):
                x[(mid, ki)] = model.NewBoolVar(f"x_{mid}_{ki}")
            model.AddExactlyOne(x[(mid, ki)] for ki in range(len(cands)))
        model.Add(x[(ref_id, ref_pin)] == 1)
        return x

    def exact_elem_expr(model: Any, x: dict[tuple[str, int], Any]) -> Any:
        terms: list[Any] = []
        for mid in molecule_ids:
            if mid == ref_id:
                continue
            for ki, cand in enumerate(candidates[mid]):
                if cand.exact_element_matches:
                    terms.append(x[(mid, ki)] * cand.exact_element_matches)
        return sum(terms) if terms else 0

    def group_elem_expr(model: Any, x: dict[tuple[str, int], Any]) -> Any:
        terms: list[Any] = []
        for mid in molecule_ids:
            if mid == ref_id:
                continue
            for ki, cand in enumerate(candidates[mid]):
                if cand.group_element_matches:
                    terms.append(x[(mid, ki)] * cand.group_element_matches)
        return sum(terms) if terms else 0

    def subst_expr(model: Any, x: dict[tuple[str, int], Any], *, coarse: bool) -> Any:
        terms: list[Any] = []
        for i, mid_a in enumerate(molecule_ids):
            for mid_b in molecule_ids[i + 1 :]:
                for ka, ca in enumerate(candidates[mid_a]):
                    for kb, cb in enumerate(candidates[mid_b]):
                        w = _site_agreement(ca, cb, coarse=coarse)
                        if w:
                            terms.append(_pair_and_literal(model, x[(mid_a, ka)], x[(mid_b, kb)]) * w)
        for mid in molecule_ids:
            if mid == ref_id:
                continue
            for ki, cand in enumerate(candidates[mid]):
                anchor = _ref_anchor(cand, ref_roles, coarse=coarse)
                if anchor:
                    terms.append(x[(mid, ki)] * anchor)
        return sum(terms) if terms else 0

    if mode == "from_smarts":
        level_builders = (
            lambda model, x: exact_elem_expr(model, x),
            lambda model, x: group_elem_expr(model, x),
            lambda model, x: subst_expr(model, x, coarse=False),
            lambda model, x: subst_expr(model, x, coarse=True),
        )
    else:
        level_builders = (
            lambda model, x: subst_expr(model, x, coarse=False),
            lambda model, x: subst_expr(model, x, coarse=True),
        )

    fixed_prefix: list[int] = []
    for level, builder in enumerate(level_builders):
        model = cp_model.CpModel()
        x = add_vars_and_constraints(model)
        exprs = [level_builders[i](model, x) for i in range(level + 1)]
        for prior, value in enumerate(fixed_prefix):
            model.Add(exprs[prior] == value)
        model.Maximize(exprs[level])
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = MAX_OPTIMIZER_TIME_SECONDS
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return None
        fixed_prefix.append(int(solver.ObjectiveValue()))

    # Recover assignment at the last solved model
    model = cp_model.CpModel()
    x = add_vars_and_constraints(model)
    exprs = [builder(model, x) for builder in level_builders]
    for prior, value in enumerate(fixed_prefix):
        model.Add(exprs[prior] == value)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = MAX_OPTIMIZER_TIME_SECONDS
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    chosen: dict[str, IsomorphismCandidate] = {}
    for mid in molecule_ids:
        for ki, cand in enumerate(candidates[mid]):
            if solver.Value(x[(mid, ki)]):
                chosen[mid] = cand
                break
    return chosen if len(chosen) == len(molecule_ids) else None


def _solve_greedy(
    molecule_ids: list[str],
    candidates: dict[str, list[IsomorphismCandidate]],
    ref_roles: tuple[SubstituentRole, ...],
    *,
    ref_id: str,
    ref_pin: int,
    mode: ScaffoldElementMode,
) -> dict[str, IsomorphismCandidate] | None:
    ref_cands = candidates.get(ref_id, [])
    if not ref_cands:
        return None
    chosen: dict[str, IsomorphismCandidate] = {}
    pin = ref_pin if 0 <= ref_pin < len(ref_cands) else 0
    chosen[ref_id] = ref_cands[pin]
    for mid in molecule_ids:
        if mid == ref_id:
            continue
        best: IsomorphismCandidate | None = None
        best_key: tuple[int, ...] = ()
        for cand in candidates[mid]:
            subst = _ref_anchor(cand, ref_roles, coarse=False)
            coarse = _ref_anchor(cand, ref_roles, coarse=True)
            if mode == "from_smarts":
                key = (
                    cand.exact_element_matches,
                    cand.group_element_matches,
                    subst,
                    coarse,
                )
            else:
                key = (subst, coarse)
            if best is None or key > best_key:
                best_key = key
                best = cand
        if best is None:
            best = candidates[mid][0]
        chosen[mid] = best
    return chosen


def select_global_isomorphisms(
    molecule_ids: list[str],
    candidates_by_id: dict[str, list[IsomorphismCandidate]],
    ref_id: str,
    ref_match: Sequence[int],
    ref_mol: Chem.Mol,
    *,
    mode: ScaffoldElementMode,
) -> dict[str, tuple[int, ...]] | None:
    if ref_id not in candidates_by_id or not candidates_by_id[ref_id]:
        return None
    ordered = [ref_id] + [m for m in molecule_ids if m != ref_id and candidates_by_id.get(m)]
    ref_roles = _substituents_for_match(ref_mol, ref_match)
    ref_pin = 0
    target = tuple(ref_match)
    for idx, cand in enumerate(candidates_by_id[ref_id]):
        if cand.match == target:
            ref_pin = idx
            break

    if all(len(candidates_by_id.get(m, [])) <= 1 for m in ordered):
        return {m: candidates_by_id[m][0].match for m in ordered if candidates_by_id.get(m)}

    picked = _solve_with_cpsat(
        ordered, candidates_by_id, ref_roles, ref_id=ref_id, ref_pin=ref_pin, mode=mode
    )
    if picked is None:
        picked = _solve_greedy(
            ordered, candidates_by_id, ref_roles, ref_id=ref_id, ref_pin=ref_pin, mode=mode
        )
    if picked is None:
        return None
    return {mid: picked[mid].match for mid in ordered if mid in picked}


def reference_core_match(
    ref_mol: Chem.Mol,
    query: Chem.Mol,
) -> tuple[int, ...]:
    matches = ref_mol.GetSubstructMatches(query, uniquify=True)
    if not matches:
        return ()
    return max(matches, key=len)


def pick_scaffold_matches(
    ingested_by_id: dict[str, Any],
    reference_id: str,
    core_smarts: str,
    *,
    scaffold_element_mode: str = "from_smarts",
    ignore_bond_order: bool = False,
    progress: Any | None = None,
) -> tuple[Chem.Mol | None, dict[str, tuple[int, ...]], list[str]]:
    """Enumerate isomorphisms of the existing core SMARTS, then pick globally.

    Returns ``(query, match_by_molecule_id, errors)``. Analogs that lack the
    core are listed in ``errors``; remaining molecules are still selected.
    """
    from wetlabdb.sar.pipeline.ingestion import IngestedMolecule

    mode = normalize_scaffold_element_mode(scaffold_element_mode)
    errors: list[str] = []
    ref = ingested_by_id.get(reference_id)
    if ref is None or not isinstance(ref, IngestedMolecule):
        return None, {}, [f"missing reference {reference_id}"]

    query = match_query_from_smarts(
        core_smarts, mode=mode, ignore_bond_order=ignore_bond_order
    )
    if query is None:
        return None, {}, ["invalid core_smarts"]

    ref_match = reference_core_match(ref.draw_mol, query)
    if not ref_match:
        return None, {}, [f"reference {reference_id} missing core"]

    candidates_by_id: dict[str, list[IsomorphismCandidate]] = {}
    items = [
        (mid, item)
        for mid, item in ingested_by_id.items()
        if isinstance(item, IngestedMolecule)
    ]
    n = len(items)
    if progress:
        progress("mapping", 0, n)
    for i, (mid, item) in enumerate(items, 1):
        cands = enumerate_isomorphism_candidates(
            item.draw_mol,
            query,
            ref.draw_mol,
            ref_match,
            mode=mode,
        )
        if not cands:
            errors.append(f"{mid}: core not found")
        else:
            candidates_by_id[mid] = cands
        if progress:
            progress("mapping", i, n)

    if reference_id not in candidates_by_id:
        return query, {}, errors or [f"reference {reference_id} missing core"]
    if not candidates_by_id:
        return query, {}, errors

    if progress:
        progress("optimize", 0, 1)
    mol_ids = [mid for mid in ingested_by_id if mid in candidates_by_id]
    chosen = select_global_isomorphisms(
        mol_ids,
        candidates_by_id,
        reference_id,
        ref_match,
        ref.draw_mol,
        mode=mode,
    )
    if progress:
        progress("optimize", 1, 1)
    if chosen is None:
        return query, {}, [*errors, "scaffold isomorphism selection failed"]
    return query, chosen, errors


__all__ = [
    "IsomorphismCandidate",
    "ScaffoldElementMode",
    "element_agnostic_query",
    "enumerate_isomorphism_candidates",
    "match_query_from_smarts",
    "normalize_scaffold_element_mode",
    "periodic_group",
    "pick_scaffold_matches",
    "reference_core_match",
    "select_global_isomorphisms",
]
