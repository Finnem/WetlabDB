"""Core picking: subgraph SMARTS and heteroatom generalization."""

from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import AllChem

from wetlabdb.chem.smiles import parse_smiles, perceive_aromaticity
from wetlabdb.sar.pipeline.core_pick import (
    _rotate_conformer_clockwise,
    depict_structure,
    extract_atom_subset,
    generalize_core_from_analog,
    guess_shared_core,
    match_atom_indices,
    preview_core,
    rotate_poses,
    smarts_from_core,
)


def _mol(smiles: str):
    mol = parse_smiles(smiles)
    assert mol is not None
    perceive_aromaticity(mol)
    return mol


def test_benzene_core_matches_chlorobenzene_not_pyridine():
    benzene = _mol("c1ccccc1")
    core = list(range(6))
    smarts = smarts_from_core(benzene, core)
    assert smarts
    assert match_atom_indices(_mol("Clc1ccccc1"), smarts)
    assert not match_atom_indices(_mol("n1ccccc1"), smarts)


def test_ignore_bond_order_matches_aliphatic_ring():
    smarts = "c1ccccc1"
    assert not match_atom_indices(_mol("C1CCCCC1"), smarts)
    assert match_atom_indices(_mol("C1CCCCC1"), smarts, ignore_bond_order=True)
    assert match_atom_indices(_mol("Clc1ccccc1"), smarts, ignore_bond_order=True)
    assert not match_atom_indices(_mol("n1ccccc1"), smarts, ignore_bond_order=True)
    preview = preview_core(
        "c1ccccc1",
        list(range(6)),
        [{"id": "ch", "smiles": "C1CCCCC1"}],
        ignore_bond_order=True,
    )
    assert preview["matches"][0]["matched"]
    assert "~" not in preview["smarts"]
    off = preview_core(
        "c1ccccc1",
        list(range(6)),
        [{"id": "ch", "smiles": "C1CCCCC1"}],
        ignore_bond_order=False,
    )
    assert off["smarts"] == preview["smarts"]


def test_depict_nitro_keeps_charge_separated_form():
    """IUPAC / ACS nitro is [N+](=O)[O-], not pentavalent N(=O)=O."""
    drawn = depict_structure("O=[N+]([O-])c1ccccc1")
    assert drawn is not None
    nitrogens = [a for a in drawn["atoms"] if a["symbol"] == "N"]
    oxygens = [a for a in drawn["atoms"] if a["symbol"] == "O"]
    assert any(a["charge"] == 1 for a in nitrogens)
    assert any(a["charge"] == -1 for a in oxygens)
    assert "stroke-dasharray:1," not in drawn["svg"]


def test_depict_does_not_draw_unspecified_bonds():
    drawn = depict_structure("c1ccccc1")
    assert drawn is not None
    assert "stroke-dasharray:1," not in drawn["svg"]
    assert "stroke-dasharray:6,4" not in drawn["svg"]
    fragment = depict_structure("Clc1ccccc1", fragment_atoms=[1, 2, 3, 4, 5, 6])
    assert fragment is not None
    assert "stroke-dasharray:1," not in fragment["svg"]
    assert depict_structure("[#6]1~[#6]~[#6]~[#6]~[#6]~[#6]~1") is None


def test_aliphatic_ester_oxygen_stays_literal_oxygen():
    smiles = "CCOC(=O)c1cscn1"
    mol = _mol(smiles)
    alkoxy = next(
        a.GetIdx()
        for a in mol.GetAtoms()
        if a.GetAtomicNum() == 8 and not a.GetIsAromatic() and a.GetDegree() == 2
    )
    smarts = smarts_from_core(mol, [alkoxy])
    assert smarts
    assert "#6,#7,#8" not in smarts
    assert "[#8]" in smarts or smarts in ("O", "[O]")
    preview = preview_core(smiles, [alkoxy], [{"id": "self", "smiles": smiles}])
    assert preview["connected"] is True
    assert "#6,#7,#8" not in preview["smarts"]
    carbonyl = next(
        a.GetIdx()
        for a in mol.GetAtoms()
        if a.GetAtomicNum() == 6
        and not a.GetIsAromatic()
        and sum(n.GetAtomicNum() == 8 for n in a.GetNeighbors()) == 2
    )
    oxygens = [
        n.GetIdx()
        for n in mol.GetAtomWithIdx(carbonyl).GetNeighbors()
        if n.GetAtomicNum() == 8
    ]
    ester = [alkoxy] + [carbonyl] + [o for o in oxygens if o != alkoxy]
    preview = preview_core(smiles, ester, [{"id": "self", "smiles": smiles}])
    assert preview["connected"] is True, preview
    assert preview["smarts"]
    assert "#6,#7,#8" not in preview["smarts"]
    assert match_atom_indices(mol, preview["smarts"])
    assert depict_structure(smiles, fragment_atoms=ester) is not None
    ipso = next(
        n.GetIdx()
        for n in mol.GetAtomWithIdx(carbonyl).GetNeighbors()
        if n.GetIsAromatic()
    )
    drawn = depict_structure(smiles, fragment_atoms=[*ester, ipso])
    assert drawn is not None
    from wetlabdb.sar.pipeline.fixed_core import run_same_scaffold

    result = run_same_scaffold(
        {
            "id": "ester-core",
            "comparison": {
                "mode": "same_scaffold",
                "reference": "a",
                "core_smarts": preview["smarts"],
            },
            "molecules": [
                {"id": "a", "smiles": smiles},
                {"id": "b", "smiles": "CCOC(=O)c1cccs1"},
            ],
        }
    )
    assert result.status == "OPTIMAL", result.user_message


def test_clicking_pyridine_nitrogen_generalizes_ring_atom():
    preview = preview_core(
        "c1ccccc1",
        list(range(6)),
        [
            {"id": "phcl", "smiles": "Clc1ccccc1"},
            {"id": "pyr", "smiles": "n1ccccc1"},
        ],
        atom_modes={0: "group"},
    )
    assert preview["smarts"]
    assert preview["generalized_atoms"], preview
    by_id = {m["id"]: m for m in preview["matches"]}
    assert by_id["phcl"]["matched"]
    assert by_id["pyr"]["matched"], preview
    assert "#" in preview["smarts"] or "," in preview["smarts"]


def test_disconnected_core_rejected():
    preview = preview_core("CCc1ccccc1", [0, 5], [])
    assert preview["smarts"] == ""
    assert preview["connected"] is False


def test_empty_core_has_hint_message():
    preview = preview_core("c1ccccc1", [], [{"id": "a", "smiles": "c1ccccc1"}])
    assert preview["smarts"] == ""
    assert "Click atoms" in preview["message"]
    assert "reference structure" in preview["message"]


def test_core_can_be_defined_on_any_molecule():
    preview = preview_core(
        "Clc1ccccc1",
        [1, 2, 3, 4, 5, 6],
        [
            {"id": "clph", "smiles": "Clc1ccccc1"},
            {"id": "ph", "smiles": "c1ccccc1"},
        ],
    )
    assert preview["connected"] is True
    assert preview["smarts"]
    by_id = {m["id"]: m for m in preview["matches"]}
    assert by_id["clph"]["matched"]
    assert by_id["ph"]["matched"]


def test_depict_returns_svg_and_atom_coords():
    body = depict_structure("c1ccccc1", width=200, height=160, selected=[0, 1, 2])
    assert body is not None
    assert "<svg" in body["svg"]
    assert len(body["atoms"]) == 6
    assert body["atoms"][0]["selected"] is True
    assert "x" in body["atoms"][0]
    assert body["atoms"][0]["neighbors"]
    assert body["width"] > 0
    assert body["height"] > 0


def test_depict_core_fragment_is_smaller_than_parent():
    full = depict_structure("Clc1ccccc1")
    core = depict_structure("Clc1ccccc1", fragment_atoms=[1, 2, 3, 4, 5, 6])
    assert full is not None and core is not None
    assert len(core["atoms"]) == 6
    frag = extract_atom_subset(_mol("Clc1ccccc1"), [1, 2, 3, 4, 5, 6])
    assert frag is not None
    assert frag.GetNumAtoms() == 6


def test_guess_drops_shared_halogen_from_core():
    guess = guess_shared_core(
        [
            {"id": "cl", "smiles": "Clc1ccccc1"},
            {"id": "br", "smiles": "Brc1ccccc1"},
        ],
        reference_id="cl",
    )
    assert guess["smarts"], guess
    assert len(guess["core_atoms"]) == 6
    assert "Cl" not in guess["smarts"]
    assert "Br" not in guess["smarts"]
    assert match_atom_indices(_mol("Fc1ccccc1"), guess["smarts"])


def test_guess_methoxy_and_chloro_share_phenyl():
    guess = guess_shared_core(
        [
            {"id": "ome", "smiles": "COc1ccccc1"},
            {"id": "cl", "smiles": "Clc1ccccc1"},
        ]
    )
    assert len(guess["core_atoms"]) == 6, guess
    assert match_atom_indices(_mol("c1ccccc1"), guess["smarts"])


def test_guess_single_molecule_uses_ring_system():
    guess = guess_shared_core([{"id": "cl", "smiles": "Clc1ccccc1"}])
    assert len(guess["core_atoms"]) == 6
    assert "Cl" not in guess["smarts"]


def test_depict_molblock_preserves_orientation():
    mol = _mol("Clc1ccccc1")
    AllChem.Compute2DCoords(mol)
    conf = mol.GetConformer()
    for i in range(mol.GetNumAtoms()):
        p = conf.GetAtomPosition(i)
        conf.SetAtomPosition(i, (-p.y, p.x, 0.0))
    block = Chem.MolToMolBlock(mol)
    independent = depict_structure("Clc1ccccc1")
    aligned = depict_structure("Clc1ccccc1", molblock=block)
    assert independent is not None and aligned is not None
    assert independent["svg"] != aligned["svg"]


def test_depict_nitro_keeps_oxygen_labels():
    smiles = "Clc1nc2ccc([N+](=O)[O-])cc2s1"
    drawn = depict_structure(smiles)
    assert drawn is not None
    assert len(drawn["atoms"]) == Chem.MolFromSmiles(smiles).GetNumAtoms()
    oxygens = [a for a in drawn["atoms"] if a["symbol"] == "O"]
    assert len(oxygens) == 2
    dx = oxygens[0]["x"] - oxygens[1]["x"]
    dy = oxygens[0]["y"] - oxygens[1]["y"]
    assert dx * dx + dy * dy > 4


def test_rotate_poses_changes_coordinates():
    mol = _mol("Clc1ccccc1")
    AllChem.Compute2DCoords(mol)
    block = Chem.MolToMolBlock(mol, kekulize=False)
    poses = rotate_poses([{"id": "a", "smiles": "Clc1ccccc1", "molblock": block}], 45)
    assert poses[0]["molblock"]
    assert poses[0]["molblock"] != block
    original = depict_structure("Clc1ccccc1", molblock=block)
    rotated = depict_structure("Clc1ccccc1", molblock=poses[0]["molblock"])
    assert original is not None and rotated is not None
    assert original["svg"] != rotated["svg"]


def test_rotate_poses_keeps_aligned_coords_not_smiles_layout():
    """MolToMolBlock starts with a blank name line; stripping it used to
    make parse fail and rotate a fresh SMILES depiction instead."""
    mol = _mol("Clc1cc(C)ccc1")
    AllChem.Compute2DCoords(mol)
    conf = mol.GetConformer()
    for i in range(mol.GetNumAtoms()):
        p = conf.GetAtomPosition(i)
        conf.SetAtomPosition(i, (-p.y, p.x, 0.0))
    block = Chem.MolToMolBlock(mol, kekulize=False)
    assert block.startswith("\n")
    expected = Chem.Mol(mol)
    _rotate_conformer_clockwise(expected, 35)
    exp = expected.GetConformer().GetAtomPosition(0)
    poses = rotate_poses([{"id": "a", "smiles": "Clc1cc(C)ccc1", "molblock": block}], 35)
    got = Chem.MolFromMolBlock(poses[0]["molblock"], sanitize=True, removeHs=False)
    assert got is not None and got.GetNumConformers()
    pt = got.GetConformer().GetAtomPosition(0)
    assert abs(pt.x - exp.x) < 0.05
    assert abs(pt.y - exp.y) < 0.05
    # JSON clients often .trim(); parser must still recover the pose.
    poses_trim = rotate_poses(
        [{"id": "a", "smiles": "Clc1cc(C)ccc1", "molblock": block.strip()}], 35
    )
    got_trim = Chem.MolFromMolBlock(poses_trim[0]["molblock"], sanitize=True, removeHs=False)
    pt_trim = got_trim.GetConformer().GetAtomPosition(0)
    assert abs(pt_trim.x - exp.x) < 0.05
    assert abs(pt_trim.y - exp.y) < 0.05


def test_same_scaffold_keeps_rotated_reference_pose():
    from wetlabdb.sar.pipeline.fixed_core import run_same_scaffold

    mol = _mol("Clc1ccccc1")
    AllChem.Compute2DCoords(mol)
    block = Chem.MolToMolBlock(mol, kekulize=False)
    rotated = rotate_poses([{"id": "cl", "smiles": "Clc1ccccc1", "molblock": block}], 90)[0][
        "molblock"
    ]
    expected = Chem.MolFromMolBlock(rotated, sanitize=True, removeHs=False)
    exp = expected.GetConformer().GetAtomPosition(1)
    result = run_same_scaffold(
        {
            "id": "keep-pose",
            "comparison": {
                "mode": "same_scaffold",
                "reference": "cl",
                "core_smarts": "c1ccccc1",
            },
            "molecules": [
                {"id": "cl", "smiles": "Clc1ccccc1", "molblock": rotated},
                {"id": "br", "smiles": "Brc1ccccc1"},
            ],
        }
    )
    assert result.status == "OPTIMAL", result.user_message
    by_id = {row.molecule_id: row for row in result.layouts}
    got = Chem.MolFromMolBlock(by_id["cl"].molblock, sanitize=True, removeHs=False)
    pt = got.GetConformer().GetAtomPosition(1)
    assert abs(pt.x - exp.x) < 0.05
    assert abs(pt.y - exp.y) < 0.05


def test_smarts_from_core_atom_modes():
    mol = _mol("COc1ccc2nc(C#N)sc2c1")
    core = match_atom_indices(mol, "c1ccc2scnc2c1")
    assert core
    s_idx = next(i for i in core if mol.GetAtomWithIdx(i).GetAtomicNum() == 16)
    exact = smarts_from_core(mol, core, atom_modes={i: "exact" for i in core})
    grouped = smarts_from_core(mol, core, atom_modes={**{i: "exact" for i in core}, s_idx: "group"})
    assert "[#16" in exact or "#16&" in exact
    assert "#8,#16,#34" in grouped
    any_smarts = smarts_from_core(mol, [s_idx], atom_modes={s_idx: "any"})
    assert "[#16" not in any_smarts and "16" not in any_smarts.split("&")[0]


def test_preview_core_group_sulfur_chalcogen_token():
    ref = "COc1ccc2nc(C#N)sc2c1"
    mol = _mol(ref)
    core = match_atom_indices(mol, "c1ccc2scnc2c1")
    s_idx = next(i for i in core if mol.GetAtomWithIdx(i).GetAtomicNum() == 16)
    preview = preview_core(
        ref,
        core,
        [{"id": "021", "smiles": "CSc1nc2ncccc2o1"}],
        atom_modes={s_idx: "group"},
    )
    assert "#8,#16,#34" in preview["smarts"]
    assert preview["atom_modes"][str(s_idx)] == "group"


def test_generalize_from_analog_pyridine_nitrogen():
    body = generalize_core_from_analog(
        "c1ccccc1",
        list(range(6)),
        {},
        "n1ccccc1",
        0,
    )
    assert body["ok"] is True
    assert body["mapped_ref_atom"] is not None
    preview = preview_core(
        "c1ccccc1",
        body["core_atoms"],
        [{"id": "pyr", "smiles": "n1ccccc1"}],
        atom_modes={int(k): v for k, v in body["atom_modes"].items()},
    )
    assert preview["matches"][0]["matched"]


def test_depict_query_labels_on_core_fragment():
    mol = _mol("COc1ccc2nc(C#N)sc2c1")
    core = match_atom_indices(mol, "c1ccc2scnc2c1")
    s_idx = next(i for i in core if mol.GetAtomWithIdx(i).GetAtomicNum() == 16)
    drawn = depict_structure(
        "COc1ccc2nc(C#N)sc2c1",
        fragment_atoms=core,
        core_atom_modes={s_idx: "group", core[0]: "exact"},
        query_labels=True,
    )
    assert drawn is not None
    labels = [a.get("query_label") for a in drawn["atoms"] if a.get("query_label")]
    assert any("O" in str(x) and "S" in str(x) for x in labels)
    exact_labels = [
        a.get("query_label")
        for a in drawn["atoms"]
        if a.get("query_label") and str(a.get("query_label")) in ("C", "N", "S", "O")
    ]
    assert exact_labels
