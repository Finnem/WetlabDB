"""ChemDraw CDXML page figures (ACS 1996).

MOL import lets ChemDraw rescale bonds to its default 30 pt length, so a
three-across ACS row overflows the 523.32 pt drawing. CDXML sets BondLength
to 14.4 pt and keeps captions in the same coordinate system.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from collections.abc import Sequence

from rdkit import Chem


def _atom_bbox(mol: Chem.Mol) -> tuple[float, float, float, float]:
    conf = mol.GetConformer()
    xs = [conf.GetAtomPosition(i).x for i in range(mol.GetNumAtoms())]
    ys = [conf.GetAtomPosition(i).y for i in range(mol.GetNumAtoms())]
    return min(xs), min(ys), max(xs), max(ys)

_ACS_BOND_PT = 14.4
_PAGE_PT_W = 595.28
_PAGE_PT_H = 841.89
_MARGIN_PT = 36.0
_CAPTION_PT = 10.0
_FONT_ID = "3"


def _xml_text(value: str) -> str:
    return value.replace("\x00", "")


def _bond_order(bond: Chem.Bond) -> str:
    kind = bond.GetBondType()
    if kind == Chem.BondType.DOUBLE:
        return "2"
    if kind == Chem.BondType.TRIPLE:
        return "3"
    if kind == Chem.BondType.AROMATIC:
        return "1.5"
    return "1"


def _bond_display(bond: Chem.Bond) -> str | None:
    direction = bond.GetBondDir()
    if direction == Chem.BondDir.BEGINWEDGE:
        return "WedgeBegin"
    if direction == Chem.BondDir.BEGINDASH:
        return "WedgedHashBegin"
    return None


def _to_cdxml_xy(x: float, y: float, top_y: float) -> tuple[float, float]:
    """RDKit y-up, origin at drawing top-left → CDXML y-down from the page origin."""
    return _MARGIN_PT + x, _MARGIN_PT + (top_y - y)


def mols_to_cdxml(
    mols: Sequence[Chem.Mol],
    names: Sequence[str],
    *,
    caption_gap_pt: float = 8.0,
    captions: Sequence[tuple[float, float, float]] | None = None,
) -> str:
    """Write ACS-1996 CDXML. ``mols`` must already be in points, y-up.

    ``captions`` are ``(x, y, cell_width)`` in the same coordinates: the
    center-top of the name, below the structure.
    """
    if len(mols) != len(names):
        raise ValueError("mols and names must be the same length")
    if not mols:
        raise ValueError("No structures to write")
    if captions is not None and len(captions) != len(mols):
        raise ValueError("captions must match mols")

    min_x, min_y, max_x, max_y = _atom_bbox(mols[0])
    for mol in mols[1:]:
        a, b, c, d = _atom_bbox(mol)
        min_x, min_y = min(min_x, a), min(min_y, b)
        max_x, max_y = max(max_x, c), max(max_y, d)
    if captions:
        for cx, cy, width in captions:
            min_y = min(min_y, cy - _CAPTION_PT)
            min_x = min(min_x, cx - width / 2.0)
            max_x = max(max_x, cx + width / 2.0)
    else:
        for mol, name in zip(mols, names):
            if not (name or "").strip():
                continue
            _a, bottom, _c, _d = _atom_bbox(mol)
            min_y = min(min_y, bottom - caption_gap_pt - _CAPTION_PT)

    top_y = max_y
    content_h = max(max_y - min_y, 1.0)
    needed = content_h + 2 * _MARGIN_PT
    height_pages = max(1, math.ceil(needed / _PAGE_PT_H - 1e-9))
    page_h = height_pages * _PAGE_PT_H

    root = ET.Element(
        "CDXML",
        {
            "BondLength": f"{_ACS_BOND_PT:.2f}",
            "BondSpacing": "18",
            "LineWidth": "0.60",
            "BoldWidth": "2.00",
            "HashSpacing": "2.50",
            "MarginWidth": "1.60",
            "CaptionSize": "10",
            "LabelSize": "10",
            "LabelFont": _FONT_ID,
            "CaptionFont": _FONT_ID,
            "CaptionFace": "0",
            "BoundingBox": f"0 0 {_PAGE_PT_W:.2f} {page_h:.2f}",
        },
    )
    colors = ET.SubElement(root, "colortable")
    ET.SubElement(colors, "color", {"r": "1", "g": "1", "b": "1"})
    ET.SubElement(colors, "color", {"r": "0", "g": "0", "b": "0"})
    fonts = ET.SubElement(root, "fonttable")
    ET.SubElement(
        fonts,
        "font",
        {"id": _FONT_ID, "charset": "iso-8859-1", "name": "Times New Roman"},
    )
    page = ET.SubElement(
        root,
        "page",
        {
            "BoundingBox": f"0 0 {_PAGE_PT_W:.2f} {page_h:.2f}",
            "WidthPages": "1",
            "HeightPages": str(height_pages),
            "HeaderPosition": "36",
            "FooterPosition": "36",
        },
    )

    next_id = 1
    for index, (mol, raw_name) in enumerate(zip(mols, names)):
        frag_id = next_id
        next_id += 1
        fragment = ET.SubElement(page, "fragment", {"id": str(frag_id)})
        atom_ids: list[int] = []
        conf = mol.GetConformer()
        for atom in mol.GetAtoms():
            aid = next_id
            next_id += 1
            atom_ids.append(aid)
            pos = conf.GetAtomPosition(atom.GetIdx())
            cx, cy = _to_cdxml_xy(pos.x, pos.y, top_y)
            node = ET.SubElement(
                fragment,
                "n",
                {
                    "id": str(aid),
                    "p": f"{cx:.2f} {cy:.2f}",
                    "Element": str(atom.GetAtomicNum()),
                },
            )
            charge = int(atom.GetFormalCharge())
            if charge:
                node.set("Charge", str(charge))
            isotope = int(atom.GetIsotope())
            if isotope:
                node.set("Isotope", str(isotope))
        for bond in mol.GetBonds():
            bid = next_id
            next_id += 1
            attrs = {
                "id": str(bid),
                "B": str(atom_ids[bond.GetBeginAtomIdx()]),
                "E": str(atom_ids[bond.GetEndAtomIdx()]),
                "Order": _bond_order(bond),
            }
            display = _bond_display(bond)
            if display:
                attrs["Display"] = display
            ET.SubElement(fragment, "b", attrs)
        name = _xml_text((raw_name or "").strip())
        if name:
            if captions is not None:
                cap_x, cap_y, cell_w = captions[index]
            else:
                left, bottom, right, _top = _atom_bbox(mol)
                cap_x = (left + right) / 2.0
                cap_y = bottom - caption_gap_pt
                cell_w = max(right - left, 72.0)
            tx, ty = _to_cdxml_xy(cap_x, cap_y, top_y)
            half = max(cell_w / 2.0, 36.0)
            text = ET.SubElement(
                page,
                "t",
                {
                    "id": str(next_id),
                    "p": f"{tx:.2f} {ty:.2f}",
                    "BoundingBox": (
                        f"{tx - half:.2f} {ty:.2f} {tx + half:.2f} {ty + _CAPTION_PT + 4:.2f}"
                    ),
                    "Justification": "Center",
                    "VerticalJustification": "Top",
                    "CaptionLineHeight": "auto",
                    "LineHeight": "auto",
                },
            )
            next_id += 1
            run = ET.SubElement(
                text,
                "s",
                {"font": _FONT_ID, "size": "10", "face": "0", "color": "0"},
            )
            run.text = name

    xml = ET.tostring(root, encoding="unicode")
    return (
        '<?xml version="1.0" encoding="UTF-8" ?>\n'
        '<!DOCTYPE CDXML SYSTEM "http://www.cambridgesoft.com/xml/cdxml.dtd">\n'
        + xml
        + "\n"
    )


__all__ = ["mols_to_cdxml"]
