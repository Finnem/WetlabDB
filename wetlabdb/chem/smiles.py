"""Lightweight SMILES / SMARTS helpers.

These wrappers keep the rest of the app from having to remember RDKit's
"returns ``None`` on failure" convention every time it parses a SMILES, and
provide a *single* implementation of "molecule -> PNG" so UI code does not
need to repeat the RDKit boilerplate.

Nothing here imports Tk; everything is unit-testable on its own.
"""

from __future__ import annotations

from typing import Literal, Sequence, Tuple

from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem.Draw import rdMolDraw2D

# Characters that strongly suggest the input is a SMARTS pattern rather than
# a plain SMILES. Matches the heuristic the original UI used.
_SMARTS_HINTS = ("[", "]", "*", "A", "!", "#")

MoleculeKind = Literal["smiles", "smarts"]


def parse_smiles(smiles: str | None):
    """Parse a SMILES string and return an RDKit ``Mol`` or ``None``.

    Never raises -- empty / falsy input maps to ``None``.
    """
    if not smiles:
        return None
    try:
        return Chem.MolFromSmiles(smiles)
    except Exception:
        return None


def parse_smarts(smarts: str | None):
    """Parse a SMARTS string and return an RDKit ``Mol`` or ``None``."""
    if not smarts:
        return None
    try:
        return Chem.MolFromSmarts(smarts)
    except Exception:
        return None


def canonicalize_smiles(smiles: str | None) -> str | None:
    """Return the canonical SMILES for ``smiles``, or ``None`` if unparsable."""
    mol = parse_smiles(smiles)
    if mol is None:
        return None
    try:
        return Chem.MolToSmiles(mol, canonical=True)
    except Exception:
        return None


def looks_like_smarts(text: str) -> bool:
    """Cheap heuristic: does ``text`` look like SMARTS rather than SMILES?"""
    return any(c in text for c in _SMARTS_HINTS)


def parse_molecule(text: str | None) -> Tuple["Chem.Mol | None", "MoleculeKind | None"]:
    """Parse ``text`` as either SMILES or SMARTS and return ``(mol, kind)``.

    The function tries the most useful interpretation first:

    * If ``text`` does *not* look like SMARTS, it tries ``MolFromSmiles`` only.
    * If ``text`` does look like SMARTS, it tries ``MolFromSmiles`` first
      (some SMARTS-ish strings, e.g. ``[nH]1cccc1``, are also valid SMILES
      and produce richer molecules) and falls back to ``MolFromSmarts``.

    Returns ``(None, None)`` for unparsable / empty input.
    """
    if not text:
        return None, None
    mol = parse_smiles(text)
    if mol is not None:
        return mol, "smiles"
    if looks_like_smarts(text):
        mol = parse_smarts(text)
        if mol is not None:
            return mol, "smarts"
    return None, None


def is_pure_smiles(mol) -> bool:
    """Return ``True`` if ``mol`` contains no query atoms or query bonds.

    A "pure" molecule can be losslessly written as SMILES via
    ``Chem.MolToSmiles``; query-bearing molecules require SMARTS.
    """
    if mol is None:
        return False
    try:
        for atom in mol.GetAtoms():
            if atom.HasQuery():
                return False
        for bond in mol.GetBonds():
            if bond.HasQuery():
                return False
    except Exception:
        return False
    return True


def mol_to_storage_string(mol) -> str | None:
    """Return the best textual representation of ``mol`` for storage.

    Pure structures are emitted as canonical SMILES; molecules with query
    atoms / bonds are emitted as SMARTS so no information is lost.

    Aromaticity is perceived first so that Kekulé-form drawings (e.g. a
    benzene ring built bond-by-bond by the 2D editor) get serialised with
    aromatic bonds. Without this, the resulting SMARTS would use ``=`` and
    ``-`` instead of ``:`` and would never match aromatic SMILES like
    ``c1ccccc1`` during substructure search.
    """
    if mol is None:
        return None
    try:
        perceive_aromaticity(mol)
        if is_pure_smiles(mol):
            return Chem.MolToSmiles(mol, canonical=True)
        return Chem.MolToSmarts(mol)
    except Exception:
        return None


def molfile_to_storage_string(molfile: str | None) -> str | None:
    """Parse a Molfile / SD block (e.g. Ketcher export) for storage.

    Ketcher typically emits Kekulé molfiles; aromaticity is perceived via
    :func:`mol_to_storage_string` so benzene is stored as ``c1ccccc1``.
    """
    if not molfile or not str(molfile).strip():
        return None
    try:
        mol = Chem.MolFromMolBlock(str(molfile), sanitize=False)
    except Exception:
        return None
    return mol_to_storage_string(mol)


def _safe_kekulize(mol) -> None:
    """Kekulize ``mol`` in place, swallowing the failures Kekulize raises on
    query atoms / unusual aromatic systems. Drawing works fine without it."""
    try:
        Chem.Kekulize(mol, clearAromaticFlags=True)
    except Exception:
        pass


def perceive_aromaticity(mol) -> None:
    """Run RDKit's aromaticity perception on ``mol`` in place.

    Safe to call on plain molecules (no-op if already aromatic), chains
    (no-op), and SMARTS-derived molecules (skipped silently if the SMARTS
    contains only query atoms / bonds, since RDKit's aromatizer does not
    rewrite query bonds).

    This is the helper to call right before serialising a molecule that was
    built bond-by-bond in Kekulé form (for example, the output of the 2D
    drawing editor) -- without it, ``MolToSmarts`` will faithfully emit the
    Kekulé bonds and the resulting SMARTS will not match aromatic SMILES.
    """
    if mol is None:
        return
    try:
        mol.UpdatePropertyCache(strict=False)
        Chem.GetSSSR(mol)
        Chem.SetAromaticity(mol, Chem.AromaticityModel.AROMATICITY_DEFAULT)
    except Exception:
        # Aromaticity perception is best-effort; some pathological inputs
        # (e.g. radicals, unusual valences) will not perceive cleanly.
        pass


def aromatize_query(query):
    """Return a copy of ``query`` (a SMARTS-parsed Mol) where simple
    atomic-number queries are rewritten as regular atoms so that aromaticity
    perception can run.

    Background: ``Chem.MolFromSmarts("[#6]1=[#6]-...")`` produces a molecule
    where every atom is a *query atom*. ``SetAromaticity`` does not modify
    query atoms / bonds, so a Kekulé-style SMARTS query never gets perceived
    as aromatic and therefore never matches an aromatic target like
    ``c1ccccc1``. This helper rebuilds the query with real atoms wherever
    safe (``[#6]`` -> carbon atom etc.) while preserving true query atoms
    (``*``, ``[!#1]``, ``A``, ``X``, complex bracketed expressions, ...).
    The bond orders are copied verbatim, then aromaticity is perceived.

    Returns the query unchanged if it has no atoms or contains nothing we
    can safely simplify.
    """
    if query is None or query.GetNumAtoms() == 0:
        return query

    new = Chem.RWMol()
    new_idx: dict[int, int] = {}
    for atom in query.GetAtoms():
        z = atom.GetAtomicNum()
        smarts = atom.GetSmarts()
        # Only rewrite atoms whose SMARTS is exactly a plain element symbol
        # or a bare atomic-number query (``[#6]``). Anything more complex
        # (charges, isotopes, recursive SMARTS, OR-lists, ...) is preserved
        # as-is so we don't accidentally drop semantics.
        if z > 0 and smarts in (
            atom.GetSymbol(),
            atom.GetSymbol().lower(),
            f"[#{z}]",
            f"[{atom.GetSymbol()}]",
            f"[{atom.GetSymbol().lower()}]",
        ):
            new_atom = Chem.Atom(z)
        else:
            new_atom = atom
        new_idx[atom.GetIdx()] = new.AddAtom(new_atom)

    for bond in query.GetBonds():
        new.AddBond(
            new_idx[bond.GetBeginAtomIdx()],
            new_idx[bond.GetEndAtomIdx()],
            bond.GetBondType(),
        )

    out = new.GetMol()
    perceive_aromaticity(out)
    return out


def parse_smarts_for_search(smarts: str | None):
    """Parse a SMARTS pattern intended for substructure search.

    Identical to :func:`parse_smarts`, but additionally aromatizes the query
    via :func:`aromatize_query` so Kekulé patterns from the 2D editor (or
    legacy data) match aromatic SMILES targets.
    """
    query = parse_smarts(smarts)
    if query is None:
        return None
    return aromatize_query(query)


def render_to_png_bytes(
    smiles: str | None,
    width: int = 300,
    height: int = 300,
    *,
    kekulize: bool = True,
    centre: bool = True,
    highlight_atoms: Sequence[int] | None = None,
    highlight_bonds: Sequence[int] | None = None,
    background: Tuple[float, float, float, float] | None = None,
) -> bytes | None:
    """Render ``smiles`` (SMILES or SMARTS) to a PNG bytestring.

    Returns ``None`` on parse / draw failure -- callers should handle that
    rather than crashing.

    Parameters
    ----------
    smiles:
        Either a SMILES or SMARTS string. SMARTS is auto-detected via
        :func:`looks_like_smarts` and parsed accordingly.
    width, height:
        Canvas dimensions in pixels.
    kekulize:
        If ``True`` (default) the molecule is kekulized before drawing,
        which generally produces nicer 2D depictions. Failure to kekulize
        (common with query atoms) is swallowed -- the molecule is drawn as
        aromatic instead.
    centre:
        Centre the molecule inside the canvas.
    highlight_atoms / highlight_bonds:
        Optional iterables of atom / bond indices to highlight.
    background:
        Optional ``(r, g, b, a)`` tuple in 0..1 to set as the background
        colour. ``None`` keeps RDKit's default (transparent / white).
    """
    mol, _kind = parse_molecule(smiles)
    if mol is None:
        return None
    try:
        try:
            AllChem.Compute2DCoords(mol)
        except Exception:
            # Some highly-symmetric or query-bearing molecules can fail here;
            # drawing without coords would produce nothing useful, so bail.
            return None
        if kekulize:
            _safe_kekulize(mol)
        drawer = rdMolDraw2D.MolDraw2DCairo(width, height)
        opts = drawer.drawOptions()
        if centre:
            opts.centreMoleculesBeforeDrawing = True
        if background is not None:
            opts.setBackgroundColour(background)
        kwargs = {}
        if highlight_atoms is not None:
            kwargs["highlightAtoms"] = list(highlight_atoms)
        if highlight_bonds is not None:
            kwargs["highlightBonds"] = list(highlight_bonds)
        drawer.DrawMolecule(mol, **kwargs)
        drawer.FinishDrawing()
        return drawer.GetDrawingText()
    except Exception:
        return None


__all__ = [
    "MoleculeKind",
    "aromatize_query",
    "canonicalize_smiles",
    "is_pure_smiles",
    "looks_like_smarts",
    "mol_to_storage_string",
    "molfile_to_storage_string",
    "parse_molecule",
    "parse_smarts",
    "parse_smarts_for_search",
    "parse_smiles",
    "perceive_aromaticity",
    "render_to_png_bytes",
]
