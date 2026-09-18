"""Tests for :mod:`wetlabdb.chem.smiles`."""

from __future__ import annotations

import pytest

from rdkit import Chem

from wetlabdb.chem.smiles import (
    aromatize_query,
    canonicalize_smiles,
    is_pure_smiles,
    looks_like_smarts,
    mol_to_storage_string,
    parse_molecule,
    parse_smarts,
    parse_smarts_for_search,
    parse_smiles,
    perceive_aromaticity,
    render_to_png_bytes,
    smiles_to_3d_molblock,
)


def test_parse_valid_smiles():
    mol = parse_smiles("CCO")
    assert mol is not None
    assert mol.GetNumAtoms() == 3


def test_parse_invalid_smiles_returns_none():
    assert parse_smiles("not-a-real-smiles") is None
    assert parse_smiles("") is None
    assert parse_smiles(None) is None


def test_canonicalize_normalises_equivalent_forms():
    a = canonicalize_smiles("OCC")
    b = canonicalize_smiles("CCO")
    assert a == b == "CCO"


def test_canonicalize_invalid_returns_none():
    assert canonicalize_smiles("nonsense??") is None


def test_canonicalize_aromatic():
    canon = canonicalize_smiles("c1ccccc1")
    assert canon is not None
    # Either aromatic or kekulized form is fine; round-tripping must be stable.
    assert canonicalize_smiles(canon) == canon


def test_render_to_png_bytes_returns_png_signature():
    data = render_to_png_bytes("CCO")
    assert data is not None and len(data) > 0
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "expected PNG magic bytes"


def test_render_to_png_bytes_invalid_smiles_returns_none():
    assert render_to_png_bytes("zzz??!!") is None


def test_looks_like_smarts():
    assert looks_like_smarts("[#6][#8]")
    assert looks_like_smarts("[!#1]")
    assert looks_like_smarts("C*C")
    assert not looks_like_smarts("CCO")
    assert not looks_like_smarts("c1ccccc1")


# ---------------------------------------------------------------------------
# New helpers introduced for the SMILES/SMARTS consolidation.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name, smiles, expected_atoms",
    [
        ("benzene", "c1ccccc1", 6),
        ("cyclopentane", "C1CCCC1", 5),
        ("cyclohexane", "C1CCCCC1", 6),
        ("pyrrole", "[nH]1cccc1", 5),
        ("furan", "c1ccoc1", 5),
        ("thiophene", "c1ccsc1", 5),
    ],
)
def test_ring_templates_all_parse(name, smiles, expected_atoms):
    """Every ring template button in the molecule editor must yield a Mol."""
    mol = parse_smiles(smiles)
    assert mol is not None, f"{name} ({smiles!r}) should parse via MolFromSmiles"
    assert mol.GetNumAtoms() == expected_atoms


def test_pyrrole_without_explicit_h_is_unparseable():
    """Regression for the original 'Pyrrole button does nothing' bug.

    ``n1cccc1`` is the form the broken UI passed to RDKit; it returns ``None``,
    which is exactly why the button was silently failing.
    """
    assert parse_smiles("n1cccc1") is None


def test_parse_smarts_returns_mol_for_query_pattern():
    mol = parse_smarts("[#6][!#1]")
    assert mol is not None
    assert mol.GetNumAtoms() == 2


def test_parse_smarts_invalid_returns_none():
    assert parse_smarts("not-smarts??!") is None
    assert parse_smarts("") is None
    assert parse_smarts(None) is None


def test_parse_molecule_pure_smiles_classified_as_smiles():
    mol, kind = parse_molecule("c1ccccc1")
    assert mol is not None
    assert kind == "smiles"


def test_parse_molecule_pure_smarts_classified_as_smarts():
    mol, kind = parse_molecule("[#6][!#1]")
    assert mol is not None
    assert kind == "smarts"


def test_parse_molecule_empty_returns_none():
    assert parse_molecule("") == (None, None)
    assert parse_molecule(None) == (None, None)


def test_parse_molecule_invalid_returns_none():
    assert parse_molecule("zzz??!!") == (None, None)


def test_is_pure_smiles_true_for_normal_molecule():
    assert is_pure_smiles(parse_smiles("c1ccccc1")) is True
    assert is_pure_smiles(parse_smiles("CCO")) is True


def test_is_pure_smiles_false_for_query_atoms():
    mol, _ = parse_molecule("[!#1]c1ccccc1")
    assert mol is not None
    assert is_pure_smiles(mol) is False


def test_is_pure_smiles_handles_none():
    assert is_pure_smiles(None) is False


def test_mol_to_storage_string_emits_canonical_smiles_for_pure_molecule():
    """Round-tripping a benzene drawn via the editor must NOT produce SMARTS.

    Regression for the bug where the editor always emitted SMARTS like
    ``[#6]1:[#6]:[#6]:[#6]:[#6]:[#6]:1`` even for plain molecules.
    """
    mol = parse_smiles("c1ccccc1")
    text = mol_to_storage_string(mol)
    assert text == "c1ccccc1"
    # And it must NOT look like SMARTS.
    assert not looks_like_smarts(text)


def test_mol_to_storage_string_emits_smarts_for_query_molecule():
    mol, _ = parse_molecule("[!#1]c1ccccc1")
    text = mol_to_storage_string(mol)
    assert text is not None
    assert looks_like_smarts(text), f"expected SMARTS, got {text!r}"


def test_mol_to_storage_string_handles_none():
    assert mol_to_storage_string(None) is None


def test_render_to_png_bytes_accepts_smarts():
    data = render_to_png_bytes("[#6]1ccccc1")
    assert data is not None and data[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_to_png_bytes_does_not_raise_on_wildcards():
    """Regression for the silent-Kekulize bug: wildcards used to crash the
    drawer because ``Chem.Kekulize`` raises on query atoms.
    """
    data = render_to_png_bytes("[!#1]c1ccccc1")
    # Must either return PNG bytes or ``None``; never raise.
    assert data is None or data[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_to_png_bytes_with_highlight_atoms():
    data = render_to_png_bytes("c1ccccc1", highlight_atoms=[0, 1, 2])
    assert data is not None and data[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_to_png_bytes_with_background_colour():
    data = render_to_png_bytes("CCO", background=(0.0, 0.0, 0.0, 1.0))
    assert data is not None and data[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_to_png_bytes_returns_none_for_empty_input():
    assert render_to_png_bytes("") is None
    assert render_to_png_bytes(None) is None


# ---------------------------------------------------------------------------
# Aromaticity perception for Kekule SMARTS queries.
# Regression: the 2D editor used to emit ``[#6]1=[#6]-[#6]=[#6]-[#6]=[#6]-1-*``
# for "benzene + substituent", which never matched aromatic SMILES like
# ``c1ccccc1`` because ``MolFromSmarts`` produces query bonds that the
# substructure matcher does not consider equivalent to aromatic bonds.
# ---------------------------------------------------------------------------


# The exact SMARTS the user reported as not matching anything.
_KEKULE_BENZENE_WITH_WILDCARD = "[#6]1=[#6]-[#6]=[#6]-[#6]=[#6]-1-*"


def test_perceive_aromaticity_no_op_on_aromatic_input():
    mol = parse_smiles("c1ccccc1")
    perceive_aromaticity(mol)
    # All ring atoms still aromatic, output unchanged.
    assert all(a.GetIsAromatic() for a in mol.GetAtoms())
    assert Chem.MolToSmiles(mol) == "c1ccccc1"


def test_perceive_aromaticity_no_op_on_chain():
    mol = parse_smiles("CCO")
    perceive_aromaticity(mol)
    assert Chem.MolToSmiles(mol) == "CCO"


def test_perceive_aromaticity_handles_none():
    perceive_aromaticity(None)  # must not raise


def test_aromatize_query_turns_kekule_smarts_into_aromatic_query():
    raw = parse_smarts(_KEKULE_BENZENE_WITH_WILDCARD)
    assert raw is not None
    aromatized = aromatize_query(raw)
    serialised = Chem.MolToSmarts(aromatized)
    # The bond characters should be aromatic (':') rather than single/double.
    assert ":" in serialised, f"expected aromatic bonds, got {serialised!r}"
    assert "=" not in serialised
    # The wildcard substituent must survive.
    assert "*" in serialised


def test_aromatize_query_preserves_true_query_atoms():
    raw = parse_smarts("[!#1]C(=O)[#7,#8]")
    aromatized = aromatize_query(raw)
    out = Chem.MolToSmarts(aromatized)
    # The OR-list and not-hydrogen query must still be there.
    assert "[!#1]" in out
    assert "[#7,#8]" in out


def test_aromatize_query_handles_none():
    assert aromatize_query(None) is None


@pytest.mark.parametrize(
    "label, target_smiles, expected",
    [
        ("phenol", "c1ccc(O)cc1", True),
        ("paracetamol", "CC(=O)Nc1ccc(O)cc1", True),
        ("toluene", "Cc1ccccc1", True),
        ("aniline", "Nc1ccccc1", True),
        # negative cases:
        ("cyclohexanol", "C1CCCCC1O", False),
        ("cyclohexenol", "C1=CCCCC1O", False),
        ("ethanol", "CCO", False),
        # benzene without substituent: wildcard requires at least one neighbour.
        ("bare benzene", "c1ccccc1", False),
        # heteroaromatic 6-rings should NOT match a 6-carbon aromatic query.
        ("pyridine-NH", "c1cncc(N)c1", False),
    ],
)
def test_kekule_smarts_query_matches_aromatic_targets(label, target_smiles, expected):
    """The user's exact bug: ``[#6]1=[#6]-...-*`` from the 2D editor must
    match any benzene-with-substituent target after aromatization.
    """
    query = parse_smarts_for_search(_KEKULE_BENZENE_WITH_WILDCARD)
    assert query is not None
    target = parse_smiles(target_smiles)
    assert target is not None, f"target SMILES failed to parse: {target_smiles!r}"
    assert target.HasSubstructMatch(query) is expected, (
        f"{label} ({target_smiles!r}) expected match={expected}, got opposite"
    )


def test_parse_smarts_for_search_invalid_returns_none():
    assert parse_smarts_for_search("not-a-smarts??!") is None
    assert parse_smarts_for_search("") is None
    assert parse_smarts_for_search(None) is None


def test_parse_smarts_for_search_aromatizes_pure_kekule_benzene():
    """Without a wildcard either: even pure benzene drawn in Kekule form
    must come out as an aromatic query.
    """
    q = parse_smarts_for_search("[#6]1=[#6]-[#6]=[#6]-[#6]=[#6]-1")
    assert q is not None
    target = parse_smiles("c1ccccc1")
    assert target.HasSubstructMatch(q) is True


def test_mol_to_storage_string_aromatizes_kekule_benzene_drawing():
    """The other half of the fix: a benzene ring built with Kekule bonds in
    an RWMol must serialise to aromatic SMILES, not an alternating-bond
    SMARTS like ``[#6]1=[#6]-...``.
    """
    mol = Chem.RWMol()
    for _ in range(6):
        mol.AddAtom(Chem.Atom("C"))
    mol.AddBond(0, 1, Chem.BondType.DOUBLE)
    mol.AddBond(1, 2, Chem.BondType.SINGLE)
    mol.AddBond(2, 3, Chem.BondType.DOUBLE)
    mol.AddBond(3, 4, Chem.BondType.SINGLE)
    mol.AddBond(4, 5, Chem.BondType.DOUBLE)
    mol.AddBond(5, 0, Chem.BondType.SINGLE)
    text = mol_to_storage_string(mol.GetMol())
    assert text == "c1ccccc1"


def test_mol_to_storage_string_aromatizes_kekule_benzene_with_wildcard():
    """Same as above, but with a wildcard substituent that forces the SMARTS
    branch. The aromatic bonds should still come through (':' not '=').
    """
    mol = Chem.RWMol()
    for _ in range(6):
        mol.AddAtom(Chem.Atom("C"))
    mol.AddAtom(Chem.AtomFromSmarts("*"))
    mol.AddBond(0, 1, Chem.BondType.DOUBLE)
    mol.AddBond(1, 2, Chem.BondType.SINGLE)
    mol.AddBond(2, 3, Chem.BondType.DOUBLE)
    mol.AddBond(3, 4, Chem.BondType.SINGLE)
    mol.AddBond(4, 5, Chem.BondType.DOUBLE)
    mol.AddBond(5, 0, Chem.BondType.SINGLE)
    mol.AddBond(0, 6, Chem.BondType.SINGLE)
    text = mol_to_storage_string(mol.GetMol())
    assert text is not None
    assert ":" in text and "=" not in text, (
        f"expected aromatic bonds in output, got {text!r}"
    )


def test_mol_to_storage_string_does_not_aromatize_all_single_bond_ring():
    """Critical regression: if the upstream caller hands us a 6-membered
    carbon ring made entirely of single bonds (i.e. cyclohexane), we must
    NOT pretend it's aromatic.

    This was the user-reported "draw still turns it to single bonds" bug:
    when reopening a stored ``c1ccccc1`` in the editor, every bond's
    ``GetBondTypeAsDouble() == 1.5`` was truncated to ``int(1.5) == 1``,
    so the rebuilt molecule had all-single bonds. After adding a wildcard
    the editor produced ``[#6]1-[#6]-...-1-*`` -- which is structurally
    correct for cyclohexane and rightly does NOT match aromatic targets.
    The fix must live upstream (in the editor / search), not by silently
    aromatising any 6-carbon ring.
    """
    mol = Chem.RWMol()
    for _ in range(6):
        mol.AddAtom(Chem.Atom("C"))
    for i in range(6):
        mol.AddBond(i, (i + 1) % 6, Chem.BondType.SINGLE)
    text = mol_to_storage_string(mol.GetMol())
    assert text == "C1CCCCC1", (
        f"all-single 6-ring must round-trip as cyclohexane, got {text!r}"
    )


def _simulate_editor_reopen(stored_smiles: str, *, add_wildcard: bool = False) -> str | None:
    """Mimic exactly what ``MoleculeEditorWindow.__init__`` does when it
    reopens a stored value: kekulize, extract atoms + (rounded) bond orders,
    rebuild as RWMol, optionally add a wildcard substituent on atom 0,
    then run through ``mol_to_storage_string``.
    """
    from rdkit.Chem import AllChem

    mol = parse_smiles(stored_smiles)
    if mol is None:
        return None
    AllChem.Compute2DCoords(mol)
    try:
        Chem.Kekulize(mol, clearAromaticFlags=True)
    except Exception:
        pass

    rebuilt = Chem.RWMol()
    for atom in mol.GetAtoms():
        rebuilt.AddAtom(Chem.Atom(atom.GetSymbol()))
    for bond in mol.GetBonds():
        bt = max(1, round(bond.GetBondTypeAsDouble()))
        rebuilt.AddBond(
            bond.GetBeginAtomIdx(), bond.GetEndAtomIdx(),
            Chem.BondType.values[bt],
        )

    if add_wildcard:
        w_idx = rebuilt.AddAtom(Chem.AtomFromSmarts("*"))
        rebuilt.AddBond(0, w_idx, Chem.BondType.SINGLE)

    return mol_to_storage_string(rebuilt.GetMol())


@pytest.mark.parametrize(
    "stored_smiles, expected",
    [
        # Aromatic SMILES round-trip back to aromatic SMILES (no '*').
        ("c1ccccc1", "c1ccccc1"),
        ("c1ccc(O)cc1", "Oc1ccccc1"),  # canonical form may reorder
        ("c1ccncc1", "c1ccncc1"),
        # Non-aromatic input round-trips unchanged.
        ("CCO", "CCO"),
        ("C1CCCCC1", "C1CCCCC1"),
    ],
)
def test_editor_reopen_preserves_aromaticity(stored_smiles, expected):
    """Reopening an aromatic molecule must NOT silently turn it into a
    saturated ring. Without the kekulize-before-read step, every aromatic
    bond's ``GetBondTypeAsDouble() == 1.5`` truncates to single, turning
    benzene into cyclohexane.
    """
    text = _simulate_editor_reopen(stored_smiles)
    assert text == expected


def test_editor_reopen_benzene_then_wildcard_yields_aromatic_smarts():
    """The exact scenario the user reported: open editor on a stored
    ``c1ccccc1``, add a wildcard, save. The output must use aromatic
    bonds (':') so substructure search matches aromatic targets like
    phenol -- not all-single bonds (cyclohexane-with-wildcard).
    """
    text = _simulate_editor_reopen("c1ccccc1", add_wildcard=True)
    assert text is not None, "round-trip with wildcard returned None"
    assert ":" in text, (
        f"expected aromatic bonds in output, got {text!r} "
        f"(this means the bug where reopened benzene reads as cyclohexane is back)"
    )
    assert "=" not in text, f"unexpected Kekule double bonds in {text!r}"


def test_smiles_to_3d_molblock_ethanol():
    block = smiles_to_3d_molblock("CCO")
    assert block is not None
    assert "M  END" in block
    mol = Chem.MolFromMolBlock(block, sanitize=False)
    assert mol is not None
    assert mol.GetNumConformers() == 1


def test_smiles_to_3d_molblock_invalid():
    assert smiles_to_3d_molblock("not-a-molecule") is None
