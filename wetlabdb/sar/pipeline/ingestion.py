"""Immutable molecule ingestion and identity checks."""

from __future__ import annotations

from dataclasses import dataclass

from rdkit import Chem

from wetlabdb.chem.smiles import parse_smiles, perceive_aromaticity
from wetlabdb.sar.pipeline.core_pick import _parse_pose_molblock


@dataclass(frozen=True)
class IngestedMolecule:
    molecule_id: str
    source_smiles: str
    source_mol: Chem.Mol
    draw_mol: Chem.Mol


def ingest_molecule(
    molecule_id: str,
    smiles: str,
    molblock: str | None = None,
) -> IngestedMolecule | None:
    if not smiles or not str(smiles).strip():
        return None
    text = str(smiles).strip()
    mol = parse_smiles(text)
    if mol is None:
        return None
    perceive_aromaticity(mol)
    source = Chem.Mol(mol)
    draw = Chem.Mol(mol)
    posed = _parse_pose_molblock(str(molblock or ""))
    if (
        posed is not None
        and posed.GetNumAtoms() == draw.GetNumAtoms()
        and posed.GetNumConformers()
    ):
        draw.RemoveAllConformers()
        draw.AddConformer(posed.GetConformer(), assignId=True)
    return IngestedMolecule(
        molecule_id=molecule_id,
        source_smiles=text,
        source_mol=source,
        draw_mol=draw,
    )


def identity_fingerprint(mol: Chem.Mol) -> tuple:
    """Stereo-aware identity tuple for before/after export checks."""
    return (
        Chem.MolToSmiles(mol, isomericSmiles=True, canonical=True),
        Chem.rdmolops.GetFormalCharge(mol),
        tuple(sorted(Chem.rdmolops.GetMolFrags(mol))),
    )


def identity_unchanged(before: Chem.Mol, after: Chem.Mol) -> bool:
    return identity_fingerprint(before) == identity_fingerprint(after)


def molblock_round_trip(smiles: str) -> Chem.Mol | None:
    mol = parse_smiles(smiles)
    if mol is None:
        return None
    perceive_aromaticity(mol)
    block = Chem.MolToMolBlock(mol)
    return Chem.MolFromMolBlock(block, sanitize=True, removeHs=False)


__all__ = [
    "IngestedMolecule",
    "identity_fingerprint",
    "identity_unchanged",
    "ingest_molecule",
    "molblock_round_trip",
]
