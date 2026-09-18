"""SMARTS -> concrete-molecule enumeration.

This is a port of the original ``enumerate_molecules_from_smarts`` helper from
``wetlabDB.py``. The implementation is preserved verbatim, with only debug
``print`` calls removed so that the unit tests don't pollute stdout.

The function expands a SMARTS pattern with wildcard atoms (``*``, ``[!#1]``,
``[#6,#7,#8]``-style alternatives, ...) into the cross-product of concrete
molecules using only the most common organic elements.
"""

from __future__ import annotations

import re

from rdkit import Chem


_ATOMIC_NUM_TO_ATOM = {
    6: "C",  # Carbon
    7: "N",  # Nitrogen
    8: "O",  # Oxygen
    9: "F",  # Fluorine
    15: "P",  # Phosphorus
    16: "S",  # Sulfur
    17: "Cl",  # Chlorine
    35: "Br",  # Bromine
    53: "I",  # Iodine
}

_NON_HYDROGEN = ["C", "N", "O", "F", "P", "S", "Cl", "Br", "I"]
_INCLUDING_HYDROGEN = ["H", *_NON_HYDROGEN]


def _parse_atom_pattern(pattern: str) -> list[str]:
    """Resolve a single ``[...]`` SMARTS atom expression to candidate elements."""
    if "*" in pattern:  # any atom (including H)
        return _INCLUDING_HYDROGEN
    if "A" in pattern or "a" in pattern:  # any non-H atom
        return _NON_HYDROGEN
    if "!" in pattern:
        # `[!#1]` etc. -> any non-hydrogen
        return _NON_HYDROGEN

    matches = re.findall(r"#(\d+)", pattern)
    if matches:
        return [
            _ATOMIC_NUM_TO_ATOM[int(m)]
            for m in matches
            if int(m) in _ATOMIC_NUM_TO_ATOM
        ]

    explicit = re.findall(r"([A-Z][a-z]?)", pattern)
    return list(explicit)


def _parse_smarts_topology(smarts: str) -> tuple[list[tuple[int, str]], list[tuple[int, int]]]:
    """Parse the SMARTS string into an atom list and a connection list."""
    atoms: list[tuple[int, str]] = []
    connections: list[tuple[int, int]] = []

    cleaned = smarts
    # Convert unenclosed wildcards (* or A) into bracketed form for uniform parsing.
    cleaned = re.sub(r"(?<![\[\w])(\*|A)(?![\]\w])", r"[\1]", cleaned)

    atom_pattern = r"\[([^\]]+)\]"
    all_atoms = re.findall(atom_pattern, cleaned)

    for i, atom in enumerate(all_atoms):
        atoms.append((i, atom))

    # Main-chain connections (every adjacent pair).
    for i in range(len(atoms) - 1):
        connections.append((i, i + 1))

    # Branch connections of the form `(-[X])`.
    branch_pattern = r"\((-\[[^\]]+\])\)"
    for match in re.finditer(branch_pattern, cleaned):
        branch_pos = match.start()
        atoms_before = len(re.findall(atom_pattern, cleaned[:branch_pos]))
        branch_atom_idx = atoms_before + 1
        connections.append((atoms_before - 1, branch_atom_idx))

    return atoms, connections


def enumerate_molecules_from_smarts(smarts: str) -> list:
    """Generate concrete molecules consistent with ``smarts``.

    Returns a list of unique RDKit ``Mol`` objects (canonical SMILES de-duped).
    Returns an empty list on any error so callers don't have to wrap in
    ``try``/``except``.
    """
    try:
        atoms, connections = _parse_smarts_topology(smarts)

        molecules: list = []
        seen_smiles: set[str] = set()

        def recursive_build(selected_atoms: list[str], pos: int) -> None:
            if pos >= len(atoms):
                if len(selected_atoms) >= 2:
                    try:
                        smiles = selected_atoms[0]
                        added_atoms = {0}
                        used_connections: set[tuple[int, int]] = set()

                        def add_remaining_atoms(current_pos: int) -> None:
                            nonlocal smiles
                            for start, end in connections:
                                if start == current_pos and end not in added_atoms:
                                    if (start, end) not in used_connections:
                                        if end != current_pos + 1:
                                            smiles += f"({selected_atoms[end]})"
                                        else:
                                            smiles += selected_atoms[end]
                                        added_atoms.add(end)
                                        used_connections.add((start, end))
                                        used_connections.add((end, start))
                                        add_remaining_atoms(end)

                        add_remaining_atoms(0)

                        mol = Chem.MolFromSmiles(smiles)
                        if mol:
                            canon = Chem.MolToSmiles(mol, canonical=True)
                            if canon not in seen_smiles:
                                seen_smiles.add(canon)
                                molecules.append(mol)
                    except Exception:
                        pass
                return

            for atom in _parse_atom_pattern(atoms[pos][1]):
                recursive_build(selected_atoms + [atom], pos + 1)

        recursive_build([], 0)
        return molecules

    except Exception:
        return []


__all__ = ["enumerate_molecules_from_smarts"]
