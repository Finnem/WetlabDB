"""Scaffold isomorphisms and global substituent placement optimizer."""

from __future__ import annotations

from rdkit import Chem

from wetlabdb.chem.smiles import parse_smiles, perceive_aromaticity
from wetlabdb.sar.pipeline.fixed_core import run_same_scaffold
from wetlabdb.sar.pipeline.ingestion import ingest_molecule
from wetlabdb.sar.pipeline.core_pick import (
    atom_modes_for_core,
    match_atom_indices,
    smarts_from_core,
)
from wetlabdb.sar.pipeline.isomorphisms import (
    _element_overlay_counts,
    _substituents_for_match,
    enumerate_isomorphism_candidates,
    match_query_from_smarts,
    periodic_group,
    pick_scaffold_matches,
)


def _mol(smiles: str) -> Chem.Mol:
    mol = parse_smiles(smiles)
    assert mol is not None
    perceive_aromaticity(mol)
    return mol


def _group_hetero_smarts(ref_smiles: str, core_smarts: str) -> str:
    """Core SMARTS with ring hetero positions in periodic group mode (O/S, C/N, …)."""
    mol = _mol(ref_smiles)
    hit = match_atom_indices(mol, core_smarts)
    assert hit
    modes = {
        i: "group"
        for i in hit
        if mol.GetAtomWithIdx(i).GetIsAromatic()
        and mol.GetAtomWithIdx(i).GetAtomicNum() in (6, 7, 8, 15, 16)
    }
    return smarts_from_core(mol, hit, atom_modes=atom_modes_for_core(mol, hit, modes)) or core_smarts


def test_periodic_group_halogenes():
    assert periodic_group(9) == periodic_group(17)
    assert 35 in periodic_group(17)


def test_from_smarts_matches_oxazole_with_group_smarts():
    """Explicit chalcogen group in SMARTS lets oxazole hit thiazole with O on S."""
    smarts = _group_hetero_smarts("n1csc(C)c1", "c1sccn1")
    ox = _mol("c1occn1")
    query = match_query_from_smarts(smarts, mode="from_smarts", ignore_bond_order=False)
    assert query is not None
    assert ox.HasSubstructMatch(query)

    ref = ingest_molecule("thia", "n1csc(C)c1")
    analog = ingest_molecule("ox", "n1coc(Cl)c1")
    assert ref and analog
    _, chosen, errors = pick_scaffold_matches(
        {"thia": ref, "ox": analog},
        "thia",
        smarts,
        scaffold_element_mode="from_smarts",
    )
    assert not errors
    s_qi = next(
        i for i, idx in enumerate(chosen["thia"]) if ref.draw_mol.GetAtomWithIdx(idx).GetAtomicNum() == 16
    )
    assert analog.draw_mol.GetAtomWithIdx(chosen["ox"][s_qi]).GetAtomicNum() == 8


def test_element_agnostic_matches_imidazole_on_thiazole_topology():
    imid = _mol("c1[nH]ccn1")
    query = match_query_from_smarts("c1sccn1", mode="element_agnostic", ignore_bond_order=False)
    assert query is not None
    assert imid.HasSubstructMatch(query)


def test_enumerate_benzene_core_yields_multiple_candidates():
    mol = _mol("Clc1ccccc1")
    query = Chem.MolFromSmarts("c1ccccc1")
    ref_match = mol.GetSubstructMatch(query)
    cands = enumerate_isomorphism_candidates(
        mol, query, mol, ref_match, mode="from_smarts"
    )
    assert len(cands) >= 2


def test_optimizer_prefers_large_substituent_agreement():
    ref = ingest_molecule("ref", "Clc1ccc(N2CCOCC2)cc1")
    analog = ingest_molecule("b", "Brc1ccc(N2CCOCC2)cc1")
    assert ref and analog
    _, chosen, errors = pick_scaffold_matches(
        {"ref": ref, "b": analog},
        "ref",
        "c1ccccc1",
        scaffold_element_mode="from_smarts",
    )
    assert not errors
    assert chosen
    ref_match = chosen["ref"]
    ref_subs = _substituents_for_match(ref.draw_mol, ref_match)
    ana_subs = _substituents_for_match(analog.draw_mol, chosen["b"])
    morph_key = max((s for s in ref_subs if s.key), key=lambda s: s.heavy_atoms).key
    assert morph_key
    ref_site = next(i for i, s in enumerate(ref_subs) if s.key == morph_key)
    ana_site = next(i for i, s in enumerate(ana_subs) if s.key == morph_key)
    assert ref_site == ana_site


def test_from_smarts_orients_same_elements_on_thiazole():
    """Among thiazole automorphisms, put N on N and S on S."""
    ref = ingest_molecule("ref", "n1csc(C)c1")
    analog = ingest_molecule("a", "n1csc(Cl)c1")
    assert ref and analog
    query = match_query_from_smarts("c1sccn1", mode="from_smarts", ignore_bond_order=False)
    assert query is not None
    ref_match = ref.draw_mol.GetSubstructMatch(query)
    cands = enumerate_isomorphism_candidates(
        analog.draw_mol, query, ref.draw_mol, ref_match, mode="from_smarts"
    )
    assert len(cands) >= 1
    best = max(cands, key=lambda c: (c.exact_element_matches, c.group_element_matches))
    exact, _group = _element_overlay_counts(analog.draw_mol, best.match, ref.draw_mol, ref_match)
    assert exact == len(ref_match)

    _, chosen, errors = pick_scaffold_matches(
        {"ref": ref, "a": analog},
        "ref",
        "c1sccn1",
        scaffold_element_mode="from_smarts",
    )
    assert not errors
    picked_exact, _ = _element_overlay_counts(
        analog.draw_mol, chosen["a"], ref.draw_mol, chosen["ref"]
    )
    assert picked_exact == len(chosen["ref"])


def test_from_smarts_puts_thiazole_n_on_n_not_ester():
    """Chalco009 vs Chalco004: ester overlay must not beat S-on-S / N-on-N."""
    ref = ingest_molecule("004", "[s]1cnc(c1N)C(=O)OCC")
    analog = ingest_molecule("009", "[s]1c(ncc1C(=O)OCC)C")
    assert ref and analog
    core = list(ref.draw_mol.GetRingInfo().AtomRings()[0])
    smarts = smarts_from_core(ref.draw_mol, core)
    _, chosen, errors = pick_scaffold_matches(
        {"004": ref, "009": analog},
        "004",
        smarts or "c1sccn1",
        scaffold_element_mode="from_smarts",
    )
    assert not errors
    exact, _grp = _element_overlay_counts(
        analog.draw_mol, chosen["009"], ref.draw_mol, chosen["004"]
    )
    assert exact == len(chosen["004"])


def test_fused_ring_is_not_a_substituent():
    mol = _mol("[s]1c2c(cc1C(=O)OC)cc(cc2)N")
    five = min(mol.GetRingInfo().AtomRings(), key=len)

    roles = _substituents_for_match(mol, five)
    keys = [r.key for r in roles if r.key]
    assert not any("cc" in k and "N" in k for k in keys)
    assert any("C=O" in k or "COC=O" in k for k in keys)


def test_run_same_scaffold_from_smarts_optimal():
    case = {
        "id": "iso-test",
        "comparison": {
            "reference": "ref",
            "core_smarts": "c1ccccc1",
            "mode": "same_scaffold",
            "scaffold_element_mode": "from_smarts",
            "ignore_bond_order": False,
        },
        "molecules": [
            {"id": "ref", "smiles": "Clc1ccccc1"},
            {"id": "b", "smiles": "Fc1ccccc1"},
        ],
    }
    result = run_same_scaffold(case)
    assert result.status == "OPTIMAL"
    assert result.details.get("scaffold_element_mode") == "from_smarts"
    assert len(result.layouts) == 2


def test_same_scaffold_reports_progress_phases():
    events: list[tuple[str, int, int]] = []

    def progress(phase: str, done: int, total: int) -> None:
        events.append((phase, done, total))

    case = {
        "id": "iso-progress",
        "comparison": {
            "reference": "ref",
            "core_smarts": "c1ccccc1",
            "mode": "same_scaffold",
        },
        "molecules": [
            {"id": "ref", "smiles": "Clc1ccccc1"},
            {"id": "b", "smiles": "Fc1ccccc1"},
        ],
    }
    result = run_same_scaffold(case, progress=progress)
    assert result.status == "OPTIMAL"
    phases = [phase for phase, _done, _total in events]
    assert phases[0] == "ingest"
    assert "mapping" in phases
    assert "optimize" in phases
    assert "layout" in phases
    by_phase = {phase: (done, total) for phase, done, total in events}
    assert by_phase["ingest"] == (2, 2)
    assert by_phase["mapping"] == (2, 2)
    assert by_phase["layout"][1] == 2


def test_pick_keeps_matches_when_one_analog_lacks_core():
    ref = ingest_molecule("001", "N#Cc1nc2ccccc2s1")
    hit = ingest_molecule("002", "O=[N+]([O-])c1ccc2scnc2c1")
    miss = ingest_molecule("015", "CCOC(=O)c1c(N)sc2c1CNCC2")
    assert ref and hit and miss
    _, chosen, errors = pick_scaffold_matches(
        {"001": ref, "002": hit, "015": miss},
        "001",
        "c1ccc2scnc2c1",
        scaffold_element_mode="from_smarts",
    )
    assert chosen["001"]
    assert chosen["002"]
    assert "015" not in chosen
    assert any(e.startswith("015:") and "core not found" in e for e in errors)


def test_same_scaffold_aligns_hits_when_one_analog_lacks_core():
    case = {
        "id": "partial-core",
        "comparison": {
            "reference": "001",
            "core_smarts": "c1ccc2scnc2c1",
            "mode": "same_scaffold",
            "scaffold_element_mode": "from_smarts",
        },
        "molecules": [
            {"id": "001", "smiles": "N#Cc1nc2ccccc2s1"},
            {"id": "002", "smiles": "O=[N+]([O-])c1ccc2scnc2c1"},
            {"id": "015", "smiles": "CCOC(=O)c1c(N)sc2c1CNCC2"},
        ],
    }
    result = run_same_scaffold(case)
    ids = {row.molecule_id for row in result.layouts}
    assert ids == {"001", "002"}
    unmatched = result.details.get("unmatched") or []
    assert unmatched == ["015"]
    assert any("015:" in e and "core not found" in e for e in result.details.get("errors") or [])


def test_from_smarts_aligns_chalco021_when_smarts_has_explicit_groups():
    ref = ingest_molecule("001", "COc1ccc2nc(C#N)sc2c1")
    analog = ingest_molecule("021", "CSc1nc2ncccc2o1")
    assert ref and analog
    hit = match_atom_indices(ref.draw_mol, "c1ccc2scnc2c1")
    modes = atom_modes_for_core(ref.draw_mol, hit, {i: "group" for i in hit})
    smarts = smarts_from_core(ref.draw_mol, hit, atom_modes=modes)
    _, chosen, _ = pick_scaffold_matches(
        {"001": ref, "021": analog},
        "001",
        smarts,
        scaffold_element_mode="from_smarts",
    )
    assert "021" in chosen
    s_qi = next(
        i for i, idx in enumerate(chosen["001"]) if ref.draw_mol.GetAtomWithIdx(idx).GetAtomicNum() == 16
    )
    assert analog.draw_mol.GetAtomWithIdx(chosen["021"][s_qi]).GetAtomicNum() == 8

    case = {
        "id": "chalcogen-flip",
        "comparison": {
            "reference": "001",
            "core_smarts": smarts,
            "mode": "same_scaffold",
            "scaffold_element_mode": "from_smarts",
        },
        "molecules": [
            {"id": "001", "smiles": "COc1ccc2nc(C#N)sc2c1"},
            {"id": "021", "smiles": "CSc1nc2ncccc2o1"},
        ],
    }
    result = run_same_scaffold(case)
    by_id = {row.molecule_id: row for row in result.layouts}
    assert set(by_id) == {"001", "021"}
    ref_mol = Chem.MolFromMolBlock(by_id["001"].molblock, sanitize=True, removeHs=False)
    ox_mol = Chem.MolFromMolBlock(by_id["021"].molblock, sanitize=True, removeHs=False)
    assert ref_mol is not None and ox_mol is not None
    s_qi = next(
        i
        for i, idx in enumerate(by_id["001"].core_atom_indices)
        if ref_mol.GetAtomWithIdx(idx).GetAtomicNum() == 16
    )
    o_idx = by_id["021"].core_atom_indices[s_qi]
    assert ox_mol.GetAtomWithIdx(o_idx).GetAtomicNum() == 8
    rs = ref_mol.GetConformer().GetAtomPosition(by_id["001"].core_atom_indices[s_qi])
    oo = ox_mol.GetConformer().GetAtomPosition(o_idx)
    dist = ((rs.x - oo.x) ** 2 + (rs.y - oo.y) ** 2) ** 0.5
    assert dist < 0.05
