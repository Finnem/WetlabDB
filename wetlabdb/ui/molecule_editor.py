"""Auto-generated during the Phase 5 refactor (one class per module)."""

from __future__ import annotations

import base64
import io
import json
import logging
import os
from datetime import datetime

import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from PIL import Image, ImageTk
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem.Draw import rdMolDraw2D

from wetlabdb.storage import (
    LocalClient,
    MongoJSONEncoder,
    ObjectId,
    PYMONGO_AVAILABLE,
    coerce_id as _coerce_id,
    default_local_data_dir as _default_local_data_dir,
    get_local_client,
    get_mongo_client,
)
from wetlabdb.chem import (
    enumerate_molecules_from_smarts,
    mol_to_storage_string,
    parse_molecule,
)
from wetlabdb.config import AppConfig, CONFIG_FILENAME

logger = logging.getLogger(__name__)


class Tooltip:
    """Small hover tooltip for Tk widgets.

    Tooltips are created lazily on ``<Enter>`` and torn down on ``<Leave>``
    or ``<ButtonPress>``, so they do not leak Toplevels when the parent
    widget is destroyed.

    ``text`` may be either a plain string or a zero-arg callable returning
    a string. A callable is resolved every time the tooltip is shown, which
    lets a single tooltip track UI state (e.g. the description of the
    currently-selected item in a Combobox).
    """

    def __init__(self, widget, text, *, delay_ms=400):
        self.widget = widget
        self._text = text
        self.delay_ms = delay_ms
        self._tip = None
        self._after_id = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def _resolve_text(self):
        if callable(self._text):
            try:
                value = self._text()
            except Exception:
                return ""
        else:
            value = self._text
        return value or ""

    def _schedule(self, _event=None):
        self._cancel()
        try:
            self._after_id = self.widget.after(self.delay_ms, self._show)
        except tk.TclError:
            self._after_id = None

    def _cancel(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _show(self):
        self._after_id = None
        if self._tip is not None:
            return
        text = self._resolve_text()
        if not text:
            return
        try:
            x = self.widget.winfo_rootx() + 16
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
            tip = tk.Toplevel(self.widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")
            tk.Label(
                tip,
                text=text,
                justify="left",
                background="#ffffe0",
                foreground="#000000",
                relief="solid",
                borderwidth=1,
                font=("Arial", 9),
                padx=6,
                pady=3,
                wraplength=360,
            ).pack()
            self._tip = tip
        except tk.TclError:
            self._tip = None

    def _hide(self, _event=None):
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


_ATOM_TOOLTIPS = {
    "C": "Carbon",
    "N": "Nitrogen",
    "O": "Oxygen",
    "S": "Sulfur",
    "P": "Phosphorus",
    "F": "Fluorine",
    "Cl": "Chlorine",
    "Br": "Bromine",
    "I": "Iodine",
    "X": "Any halogen (Cl, Br, I) -- query atom",
    "A": "Any heavy atom (not H) -- query atom",
    "*": "Any atom (wildcard) -- query atom",
}


# Canonical CPK / Jmol element colors. Used to fill the per-atom marker on
# the drawing canvas so the structure is readable at a glance even before
# RDKit gets involved. Wildcard / query atoms get a neutral grey distinct
# from any real element.
_ATOM_COLORS = {
    "H":  "#FFFFFF",
    "He": "#D9FFFF",
    "Li": "#CC80FF",
    "Be": "#C2FF00",
    "B":  "#FFB5B5",
    "C":  "#909090",
    "N":  "#3050F8",
    "O":  "#FF0D0D",
    "F":  "#90E050",
    "Ne": "#B3E3F5",
    "Na": "#AB5CF2",
    "Mg": "#8AFF00",
    "Al": "#BFA6A6",
    "Si": "#F0C8A0",
    "P":  "#FF8000",
    "S":  "#FFFF30",
    "Cl": "#1FF01F",
    "Ar": "#80D1E3",
    "K":  "#8F40D4",
    "Ca": "#3DFF00",
    "Ti": "#BFC2C7",
    "V":  "#A6A6AB",
    "Cr": "#8A99C7",
    "Mn": "#9C7AC7",
    "Fe": "#E06633",
    "Co": "#F090A0",
    "Ni": "#50D050",
    "Cu": "#C88033",
    "Zn": "#7D80B0",
    "Ga": "#C28F8F",
    "Ge": "#668F8F",
    "As": "#BD80E3",
    "Se": "#FFA100",
    "Br": "#A62929",
    "Kr": "#5CB8D1",
    "Rb": "#702EB0",
    "Sr": "#00FF00",
    "Ag": "#C0C0C0",
    "Cd": "#FFD98F",
    "I":  "#940094",
    "Xe": "#429EB0",
    "Cs": "#57178F",
    "Ba": "#00C900",
    "Pt": "#D0D0E0",
    "Au": "#FFD123",
    "Hg": "#B8B8D0",
    "Pb": "#575961",
    # Wildcards / query atoms.
    "*":  "#C8C8C8",
    "X":  "#C8C8C8",
    "A":  "#C8C8C8",
    "Q":  "#C8C8C8",
}
_DEFAULT_ATOM_COLOR = "#9E9E9E"


def _atom_fill_color(symbol: str) -> str:
    """Return the canonical CPK/Jmol fill color for ``symbol``."""
    return _ATOM_COLORS.get(symbol, _DEFAULT_ATOM_COLOR)


def _text_color_for(bg_hex: str) -> str:
    """Pick ``'black'`` or ``'white'`` text for best contrast on ``bg_hex``.

    Uses WCAG-style relative luminance (with sRGB gamma) so the threshold
    matches human perception rather than a naive RGB average. Anything below
    ~0.5 luminance gets white text, everything above gets black.
    """
    h = bg_hex.lstrip("#")
    if len(h) != 6:
        return "black"
    try:
        r = int(h[0:2], 16) / 255.0
        g = int(h[2:4], 16) / 255.0
        b = int(h[4:6], 16) / 255.0
    except ValueError:
        return "black"

    def _linear(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    luminance = 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)
    return "white" if luminance < 0.5 else "black"


class MoleculeDrawingCanvas(tk.Canvas):
    def __init__(self, parent, smiles_var, **kwargs):
        """
        Initialize an interactive molecule drawing canvas
        
        Args:
            parent: Parent widget
            smiles_var: tkinter.StringVar that will be updated with the SMILES string
        """
        super().__init__(parent, **kwargs)
        self.smiles_var = smiles_var
        
        # Make canvas focusable
        self.configure(takefocus=1)
        
        # Drawing state
        self.atoms = []  # List of (x, y, symbol) tuples
        self.bonds = []  # List of (start_idx, end_idx, type) tuples
        self.current_atom = "C"  # Default atom type
        self.current_bond = 1    # Default bond type (single)
        self.selected_atom = None
        self.drawing_bond = False
        self.start_atom = None
        
        # Edit mode state
        self.edit_mode = False
        self.selected_item = None  # Can be 'atom' or 'bond'
        self.selected_index = None
        self.dragging = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.panning = False
        self.pan_start_x = 0
        self.pan_start_y = 0

        # Hit-test cache for ring aromaticity indicators. Each entry is
        # ``(cx, cy, [atom_indices], is_aromatic)``. Repopulated by
        # ``_draw_canvas`` while in edit mode and consulted by ``_on_click``.
        self._ring_indicators = []
        
        # Create toolbar for atom selection
        self.toolbar = self.create_toolbar(parent)
        
        # Create ring toolbar
        self.ring_toolbar = self.create_ring_toolbar(parent)
        
        # Pack the canvas after creating the toolbars
        self.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Bind mouse events
        self.bind("<Button-1>", self._on_click)
        self.bind("<Button-2>", self._on_middle_click)
        self.bind("<Button-3>", self._on_right_click)
        self.bind("<Motion>", self._on_motion)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<B2-Motion>", self._on_middle_drag)
        self.bind("<ButtonRelease-2>", self._on_middle_release)
        
        # Bind keyboard shortcuts
        self.bind("<Key>", self._on_key_press)
        
        # Set initial focus
        self.focus_set()
        
        # Initial display
        self._draw_canvas()

    def create_toolbar(self, parent):
        """Create a toolbar with atom and bond type selection"""
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill='x', pady=(0, 5))  # Pack before canvas with some padding

        # First row for basic controls
        first_row = ttk.Frame(toolbar)
        first_row.pack(fill='x', pady=(0, 5))

        # Mode selection
        ttk.Label(first_row, text="Mode:").pack(side='left', padx=5)
        self.mode_var = tk.StringVar(value="draw")
        draw_btn = ttk.Radiobutton(first_row, text="Draw", value="draw",
                                   variable=self.mode_var,
                                   command=self._update_mode)
        draw_btn.pack(side='left', padx=2)
        Tooltip(draw_btn, "Draw mode (D)\nClick empty space to add atoms,\nclick two atoms to draw a bond.")

        edit_btn = ttk.Radiobutton(first_row, text="Edit", value="edit",
                                   variable=self.mode_var,
                                   command=self._update_mode)
        edit_btn.pack(side='left', padx=2)
        Tooltip(edit_btn, "Edit mode (E)\nClick to select atoms/bonds,\ndrag to move atoms,\nright-click to delete.")

        # Atom selection
        ttk.Label(first_row, text="Atom:").pack(side='left', padx=5)
        atoms = ["C", "N", "O", "S", "P", "F", "Cl", "Br", "I", "X", "A", "*"]
        self.atom_var = tk.StringVar(value="C")
        for atom in atoms:
            btn = ttk.Radiobutton(first_row, text=atom, value=atom,
                                  variable=self.atom_var,
                                  command=self._update_current_atom)
            btn.pack(side='left', padx=2)
            Tooltip(btn, _ATOM_TOOLTIPS.get(atom, atom))

        # Add dropdown for additional elements
        ttk.Label(first_row, text="More:").pack(side='left', padx=5)
        additional_elements = [
            "H", "He", "Li", "Be", "B", "Ne", "Na", "Mg", "Al", "Si", "Ar", "K", "Ca",
            "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn", "Ga", "Ge", "As",
            "Se", "Kr", "Rb", "Sr", "Y", "Zr", "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag",
            "Cd", "In", "Sn", "Sb", "Te", "Xe", "Cs", "Ba", "La", "Ce", "Pr", "Nd", "Pm",
            "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu", "Hf", "Ta", "W",
            "Re", "Os", "Ir", "Pt", "Au", "Hg", "Tl", "Pb", "Bi", "Po", "At", "Rn", "Fr",
            "Ra", "Ac", "Th", "Pa", "U", "Np", "Pu", "Am", "Cm", "Bk", "Cf", "Es", "Fm",
            "Md", "No", "Lr", "Rf", "Db", "Sg", "Bh", "Hs", "Mt", "Ds", "Rg", "Cn", "Nh",
            "Fl", "Mc", "Lv", "Ts", "Og"
        ]
        # Sort elements by atomic number
        additional_elements.sort(key=lambda x: Chem.GetPeriodicTable().GetAtomicNumber(x))
        self.additional_atom_var = tk.StringVar(value=additional_elements[0])
        additional_menu = ttk.OptionMenu(first_row, self.additional_atom_var, additional_elements[0],
                                       *additional_elements, command=self._update_additional_atom)
        additional_menu.pack(side='left', padx=2)
        Tooltip(additional_menu, "Pick a less common element to use as the current atom.")

        # Bond selection
        ttk.Label(first_row, text="Bond:").pack(side='left', padx=5)
        bonds = [(1, "Single", "Single bond (1)"),
                 (2, "Double", "Double bond (2)"),
                 (3, "Triple", "Triple bond (3)")]
        self.bond_var = tk.IntVar(value=1)
        for bond_type, name, hint in bonds:
            btn = ttk.Radiobutton(first_row, text=name, value=bond_type,
                                  variable=self.bond_var,
                                  command=self._update_current_bond)
            btn.pack(side='left', padx=2)
            Tooltip(btn, hint)

        # Clean Up / Clear buttons (right-aligned).
        cleanup_btn = ttk.Button(first_row, text="Clean Up", command=self._cleanup_molecule)
        cleanup_btn.pack(side='right', padx=5)
        Tooltip(cleanup_btn, "Auto-arrange the molecule using RDKit's 2D coordinate generator.")

        clear_btn = ttk.Button(first_row, text="Clear", command=self.clear_drawing)
        clear_btn.pack(side='right', padx=5)
        Tooltip(clear_btn, "Remove all atoms and bonds from the canvas.")

        # Second row for edit-mode controls (initially hidden). Holds both
        # the charge editor and the "cycle bond order on click" toggle, since
        # both only make sense while editing existing structure.
        self.charge_frame = ttk.Frame(toolbar)
        ttk.Label(self.charge_frame, text="Atom Charge:").pack(side='left', padx=5)
        dec_btn = ttk.Button(self.charge_frame, text="-", command=self._decrease_charge)
        dec_btn.pack(side='left', padx=2)
        Tooltip(dec_btn, "Decrease formal charge of the selected atom by 1.")
        self.charge_label = ttk.Label(self.charge_frame, text="0")
        self.charge_label.pack(side='left', padx=2)
        inc_btn = ttk.Button(self.charge_frame, text="+", command=self._increase_charge)
        inc_btn.pack(side='left', padx=2)
        Tooltip(inc_btn, "Increase formal charge of the selected atom by 1.")

        # Cycle bond-order toggle: when ON, clicking a bond in edit mode
        # cycles its order (single -> double -> triple -> single) instead
        # of merely selecting it. Lets the user redraw bond multiplicity
        # without round-tripping through the radio buttons. On by default
        # because cycling is the action people reach for far more often
        # than just selecting a bond.
        self.iterate_bond_var = tk.BooleanVar(value=True)
        ttk.Separator(self.charge_frame, orient='vertical').pack(
            side='left', fill='y', padx=10
        )
        iterate_btn = ttk.Checkbutton(
            self.charge_frame,
            text="Cycle bond order on click",
            variable=self.iterate_bond_var,
        )
        iterate_btn.pack(side='left', padx=5)
        Tooltip(
            iterate_btn,
            "When ON, clicking a bond in Edit mode cycles its order:\n"
            "single -> double -> triple -> single.\n"
            "When OFF, clicking just selects the bond.",
        )

        # Always-visible shortcut hint so users discover the keyboard / mouse
        # bindings without having to hover every button.
        hint_row = ttk.Frame(toolbar)
        hint_row.pack(fill='x', pady=(2, 0))
        ttk.Label(
            hint_row,
            text=(
                "Shortcuts: D = Draw, E = Edit  -  "
                "Left-click: add atom / draw bond  -  "
                "Right-click: delete  -  "
                "Middle-drag: pan canvas  -  "
                "Edit mode: click ring marker to toggle aromaticity"
            ),
            foreground="#666666",
        ).pack(side='left', padx=5)

        return toolbar

    def _update_mode(self):
        """Update the current mode"""
        self.edit_mode = self.mode_var.get() == "edit"
        self.selected_item = None
        self.selected_index = None
        # Show/hide charge controls based on mode
        if self.edit_mode:
            self.charge_frame.pack(fill='x', pady=(0, 5))
        else:
            self.charge_frame.pack_forget()
        self._draw_canvas()

    def _increase_charge(self):
        """Increase the charge of the selected atom"""
        if self.edit_mode and self.selected_item == 'atom':
            x, y, symbol = self.atoms[self.selected_index]
            # Get current charge from atom properties
            charge = getattr(self, '_atom_charges', {}).get(self.selected_index, 0)
            
            # Increase charge
            charge += 1
            # Store the charge
            if not hasattr(self, '_atom_charges'):
                self._atom_charges = {}
            self._atom_charges[self.selected_index] = charge
            
            self.charge_label.configure(text=str(charge))
            self._draw_canvas()
            self._update_smiles()

    def _decrease_charge(self):
        """Decrease the charge of the selected atom"""
        if self.edit_mode and self.selected_item == 'atom':
            x, y, symbol = self.atoms[self.selected_index]
            # Get current charge from atom properties
            charge = getattr(self, '_atom_charges', {}).get(self.selected_index, 0)
            
            # Decrease charge
            charge -= 1
            # Store the charge
            if not hasattr(self, '_atom_charges'):
                self._atom_charges = {}
            self._atom_charges[self.selected_index] = charge
            
            self.charge_label.configure(text=str(charge))
            self._draw_canvas()
            self._update_smiles()

    def _on_click(self, event):
        """Handle mouse click events"""
        # Ensure canvas has focus
        self.focus_set()
        
        x, y = event.x, event.y
        
        if self.edit_mode:
            # Ring aromaticity indicator hit-test happens before atoms/bonds:
            # the marker sits at the ring centroid where there are no atoms
            # or bonds, but a generous hit radius makes it convenient to click.
            for cx, cy, ring, _aromatic in self._ring_indicators:
                if (x - cx) ** 2 + (y - cy) ** 2 <= 12 ** 2:
                    self._toggle_ring_aromaticity(ring)
                    return

            # Check if we clicked on an atom
            clicked_atom = self._find_atom_near(x, y)
            if clicked_atom is not None:
                self.selected_item = 'atom'
                self.selected_index = clicked_atom
                self.dragging = True
                self.drag_start_x = x
                self.drag_start_y = y
                # Update atom type if it's already selected
                if self.selected_item == 'atom' and self.selected_index == clicked_atom:
                    # Update the atom type radio button to match the selected atom
                    x, y, atom_type = self.atoms[clicked_atom]
                    self.atom_var.set(atom_type)
                    # Update charge display
                    charge = getattr(self, '_atom_charges', {}).get(clicked_atom, 0)
                    self.charge_label.configure(text=str(charge))
                self._draw_canvas()
                return
            
            # Check if we clicked on a bond
            for i, (start_idx, end_idx, bond_type) in enumerate(self.bonds):
                start_x, start_y, _ = self.atoms[start_idx]
                end_x, end_y, _ = self.atoms[end_idx]
                if self._point_near_line(x, y, start_x, start_y, end_x, end_y):
                    if self.iterate_bond_var.get():
                        # Cycle: 1 -> 2 -> 3 -> 1. The "% 3 + 1" trick keeps
                        # the new value in {1, 2, 3} for any positive input.
                        new_type = (bond_type % 3) + 1
                        self.bonds[i] = (start_idx, end_idx, new_type)
                        self.selected_item = 'bond'
                        self.selected_index = i
                        self.bond_var.set(new_type)
                        self._draw_canvas()
                        self._update_smiles()
                        return
                    self.selected_item = 'bond'
                    self.selected_index = i
                    # Update the bond type radio button to match the selected bond
                    self.bond_var.set(bond_type)
                    self._draw_canvas()
                    return
            
            # If we clicked on empty space, deselect
            self.selected_item = None
            self.selected_index = None
            self.charge_label.configure(text="0")
            self._draw_canvas()
            return
        
        # Drawing mode behavior
        clicked_atom = self._find_atom_near(x, y)
        if clicked_atom is not None:
            if self.drawing_bond:
                # Complete bond if different from start atom
                if clicked_atom != self.start_atom:
                    # Check if bond already exists
                    bond_exists = False
                    for start, end, _ in self.bonds:
                        if (start == self.start_atom and end == clicked_atom) or \
                           (start == clicked_atom and end == self.start_atom):
                            bond_exists = True
                            break
                    
                    if not bond_exists:
                        self.bonds.append((self.start_atom, clicked_atom, self.current_bond))
                        self._update_smiles()
                self.drawing_bond = False
                self.start_atom = None
            else:
                # Start drawing a bond
                self.drawing_bond = True
                self.start_atom = clicked_atom
        else:
            # Add new atom
            self.atoms.append((x, y, self.current_atom))
            if self.drawing_bond:
                # Create bond to the new atom
                self.bonds.append((self.start_atom, len(self.atoms) - 1, self.current_bond))
                self._update_smiles()
            self.drawing_bond = False
            self.start_atom = None
        
        self._draw_canvas()
    
    def _on_motion(self, event):
        """Handle mouse motion events"""
        if self.edit_mode and self.dragging and self.selected_item == 'atom':
            # Calculate the movement delta
            dx = event.x - self.drag_start_x
            dy = event.y - self.drag_start_y
            
            # Update atom position
            x, y, symbol = self.atoms[self.selected_index]
            self.atoms[self.selected_index] = (x + dx, y + dy, symbol)
            
            # Update drag start position
            self.drag_start_x = event.x
            self.drag_start_y = event.y
            
            # Redraw the canvas
            self._draw_canvas()
            self._update_smiles()
        elif self.drawing_bond:
            self._draw_canvas()
            # Draw temporary bond line
            start_x, start_y, _ = self.atoms[self.start_atom]
            self.create_line(start_x, start_y, event.x, event.y, fill='gray', width=2)
    
    def _on_release(self, event):
        """Handle mouse release events"""
        if self.edit_mode:
            if self.dragging and self.selected_item == 'atom':
                # Check if we released over another atom to create a bond
                x, y = event.x, event.y
                target_atom = self._find_atom_near(x, y)
                if target_atom is not None and target_atom != self.selected_index:
                    # Check if bond already exists
                    bond_exists = False
                    for start, end, _ in self.bonds:
                        if (start == self.selected_index and end == target_atom) or \
                           (start == target_atom and end == self.selected_index):
                            bond_exists = True
                            break
                    
                    if not bond_exists:
                        self.bonds.append((self.selected_index, target_atom, self.current_bond))
                        self._update_smiles()
            self.dragging = False
        elif self.drawing_bond:
            # Check if we released over an atom
            x, y = event.x, event.y
            target_atom = self._find_atom_near(x, y)
            if target_atom is not None and target_atom != self.start_atom:
                # Check if bond already exists
                bond_exists = False
                for start, end, _ in self.bonds:
                    if (start == self.start_atom and end == target_atom) or \
                       (start == target_atom and end == self.start_atom):
                        bond_exists = True
                        break
                
                if not bond_exists:
                    self.bonds.append((self.start_atom, target_atom, self.current_bond))
                    self._update_smiles()
            self.drawing_bond = False
            self.start_atom = None
            self._draw_canvas()

    def _on_middle_click(self, event):
        """Start panning the whole molecule drawing with the middle button."""
        self.focus_set()
        self.panning = True
        self.pan_start_x = event.x
        self.pan_start_y = event.y
        self.configure(cursor="fleur")

    def _on_middle_drag(self, event):
        """Move all atoms together while the middle button is held."""
        if not self.panning or not self.atoms:
            return

        dx = event.x - self.pan_start_x
        dy = event.y - self.pan_start_y
        if dx == 0 and dy == 0:
            return

        self.atoms = [(x + dx, y + dy, symbol) for x, y, symbol in self.atoms]
        self.pan_start_x = event.x
        self.pan_start_y = event.y
        self._draw_canvas()

    def _on_middle_release(self, event):
        """Finish middle-button panning."""
        self.panning = False
        self.configure(cursor="")

    # ------------------------------------------------------------------
    # Ring detection / aromaticity helpers
    # ------------------------------------------------------------------
    def _build_query_rwmol(self):
        """Build an unsanitized ``RWMol`` from the current canvas state.

        Used for ring perception and aromaticity transforms. We deliberately
        skip sanitization because the canvas may hold a half-finished or
        chemically nonsensical structure during editing -- forcing sanitization
        here would refuse to give us back ring information for perfectly
        reasonable carbocycles whose substituents happen to break valence.

        Wildcard / query symbols (``*``, ``X``, ``A``, ...) and any other
        symbol RDKit can't map to an element are stored as dummy atoms
        (atomic number 0) so ring perception still works.
        """
        if not self.atoms:
            return None
        rwmol = Chem.RWMol()
        for _x, _y, sym in self.atoms:
            try:
                rwmol.AddAtom(Chem.Atom(sym))
            except (RuntimeError, ValueError):
                rwmol.AddAtom(Chem.Atom(0))
        bond_type_map = {
            1: Chem.BondType.SINGLE,
            2: Chem.BondType.DOUBLE,
            3: Chem.BondType.TRIPLE,
        }
        for s, e, bt in self.bonds:
            try:
                rwmol.AddBond(s, e, bond_type_map.get(bt, Chem.BondType.SINGLE))
            except (RuntimeError, ValueError):
                # Duplicate bonds, or bonds referring to atoms that no longer
                # exist after a delete. Skip and keep building.
                continue
        return rwmol

    def _detect_rings(self):
        """Return a list of rings, each as a list of canvas atom indices."""
        if len(self.atoms) < 3 or not self.bonds:
            return []
        try:
            rwmol = self._build_query_rwmol()
            if rwmol is None:
                return []
            Chem.GetSSSR(rwmol)
            return [list(r) for r in rwmol.GetRingInfo().AtomRings()]
        except Exception:
            logger.debug("Ring detection failed", exc_info=True)
            return []

    @staticmethod
    def _ring_bond_pairs(ring):
        """Return the set of (unordered) atom-index pairs forming ring bonds."""
        n = len(ring)
        return {frozenset({ring[i], ring[(i + 1) % n]}) for i in range(n)}

    def _is_ring_aromatic(self, ring):
        """Heuristic: ring is treated as aromatic if any ring bond is multiple.

        We don't have a separate "aromatic" bond order in the canvas; aromatic
        rings are stored in their kekulized form (alternating single/double),
        so the presence of *any* double or triple bond inside the ring is a
        reliable signal that the user has already aromatized it.
        """
        pairs = self._ring_bond_pairs(ring)
        for s, e, bt in self.bonds:
            if frozenset({s, e}) in pairs and bt > 1:
                return True
        return False

    def _ring_centroid(self, ring):
        xs = [self.atoms[i][0] for i in ring]
        ys = [self.atoms[i][1] for i in ring]
        return sum(xs) / len(xs), sum(ys) / len(ys)

    def _toggle_ring_aromaticity(self, ring):
        """Flip a ring between kekulized-aromatic and all-single bond orders."""
        pairs = self._ring_bond_pairs(ring)
        if self._is_ring_aromatic(ring):
            # Strip aromaticity by collapsing every ring bond to single.
            new_bonds = [
                (s, e, 1) if frozenset({s, e}) in pairs else (s, e, bt)
                for s, e, bt in self.bonds
            ]
            self.bonds = new_bonds
        else:
            if not self._aromatize_ring(ring):
                messagebox.showwarning(
                    "Aromatize ring",
                    "RDKit could not perceive this ring as aromatic. The "
                    "atom types or substituents may be incompatible with an "
                    "aromatic ring of this size.",
                )
                return
        # Selection indices may now point at stale bond rows; reset to be safe.
        self.selected_item = None
        self.selected_index = None
        self._draw_canvas()
        self._update_smiles()

    def _aromatize_ring(self, ring):
        """Try to kekulize ``ring`` as aromatic, writing back canvas bonds.

        Returns ``True`` on success and updates ``self.bonds`` with the
        kekulized bond orders. Returns ``False`` if RDKit refuses to perceive
        the ring as aromatic (e.g. wrong electron count, dummy atoms, or
        substituents that break valence). The canvas is left untouched on
        failure so the caller can surface a warning.
        """
        pairs = self._ring_bond_pairs(ring)
        rwmol = Chem.RWMol()
        for _x, _y, sym in self.atoms:
            try:
                rwmol.AddAtom(Chem.Atom(sym))
            except (RuntimeError, ValueError):
                rwmol.AddAtom(Chem.Atom(0))
        bond_type_map = {
            1: Chem.BondType.SINGLE,
            2: Chem.BondType.DOUBLE,
            3: Chem.BondType.TRIPLE,
        }
        for s, e, bt in self.bonds:
            bond_type = (
                Chem.BondType.AROMATIC
                if frozenset({s, e}) in pairs
                else bond_type_map.get(bt, Chem.BondType.SINGLE)
            )
            try:
                rwmol.AddBond(s, e, bond_type)
            except (RuntimeError, ValueError):
                return False
        # Mark ring atoms aromatic. Pyrrole-like 5-rings need an explicit H
        # on the heteroatom for the Hueckel count to work, otherwise sanitize
        # rejects the structure.
        for ai in ring:
            atom = rwmol.GetAtomWithIdx(ai)
            atom.SetIsAromatic(True)
            if (
                len(ring) == 5
                and atom.GetSymbol() in {"N", "P"}
                and atom.GetFormalCharge() == 0
            ):
                degree_in_canvas = sum(
                    1 for s, e, _ in self.bonds if ai in (s, e)
                )
                if degree_in_canvas <= 2:
                    atom.SetNumExplicitHs(1)
                    atom.SetNoImplicit(True)
        try:
            Chem.SanitizeMol(rwmol)
            Chem.Kekulize(rwmol, clearAromaticFlags=True)
        except Exception:
            logger.debug(
                "Could not aromatize ring %r", ring, exc_info=True
            )
            return False
        new_bonds = []
        for s, e, bt in self.bonds:
            if frozenset({s, e}) in pairs:
                bond = rwmol.GetBondBetweenAtoms(s, e)
                if bond is not None:
                    bt = max(1, round(bond.GetBondTypeAsDouble()))
            new_bonds.append((s, e, bt))
        self.bonds = new_bonds
        return True

    def _draw_canvas(self):
        """Redraw the entire canvas"""
        self.delete('all')
        
        # Draw bonds
        for i, (start_idx, end_idx, bond_type) in enumerate(self.bonds):
            start_x, start_y, _ = self.atoms[start_idx]
            end_x, end_y, _ = self.atoms[end_idx]
            
            # Highlight selected bond
            if self.edit_mode and self.selected_item == 'bond' and self.selected_index == i:
                self.create_line(start_x, start_y, end_x, end_y, width=4, fill='blue')
            
            if bond_type == 1:
                # Single bond
                self.create_line(start_x, start_y, end_x, end_y, width=2)
            elif bond_type == 2:
                # Double bond
                dx = (end_x - start_x) * 0.1
                dy = (end_y - start_y) * 0.1
                self.create_line(start_x-dy, start_y+dx, end_x-dy, end_y+dx, width=2)
                self.create_line(start_x+dy, start_y-dx, end_x+dy, end_y-dx, width=2)
            elif bond_type == 3:
                # Triple bond
                self.create_line(start_x, start_y, end_x, end_y, width=2)
                self.create_line(start_x-2, start_y-2, end_x-2, end_y-2, width=2)
                self.create_line(start_x+2, start_y+2, end_x+2, end_y+2, width=2)
        
        # Draw ring aromaticity indicators (edit mode only). Aromatic rings
        # get a filled grey marker (RDKit-style); non-aromatic rings get a
        # blue outlined marker that hints "click me to aromatize".
        self._ring_indicators = []
        if self.edit_mode:
            for ring in self._detect_rings():
                if len(ring) < 3:
                    continue
                cx, cy = self._ring_centroid(ring)
                aromatic = self._is_ring_aromatic(ring)
                if aromatic:
                    self.create_oval(
                        cx - 8, cy - 8, cx + 8, cy + 8,
                        outline='#444444', fill='#bdbdbd', width=2,
                        tags=('ring_indicator',),
                    )
                else:
                    self.create_oval(
                        cx - 8, cy - 8, cx + 8, cy + 8,
                        outline='#3498db', width=2,
                        tags=('ring_indicator',),
                    )
                self._ring_indicators.append((cx, cy, ring, aromatic))

        # Draw atoms with canonical CPK/Jmol fill colours. The label colour
        # flips between black and white based on the relative luminance of
        # the fill so dark atoms (e.g. N, Br, I, P) stay legible.
        for i, (x, y, symbol) in enumerate(self.atoms):
            fill = _atom_fill_color(symbol)
            label_color = _text_color_for(fill)
            if self.edit_mode and self.selected_item == 'atom' and self.selected_index == i:
                # Selected atoms get a thick blue halo around the canonical
                # fill so the selection is obvious regardless of element.
                self.create_oval(x-12, y-12, x+12, y+12,
                                 fill='#1f6feb', outline='#1f6feb')
                self.create_oval(x-10, y-10, x+10, y+10,
                                 fill=fill, outline='#1f6feb', width=1)
            else:
                self.create_oval(x-10, y-10, x+10, y+10,
                                 fill=fill, outline='#222222', width=1)

            # Draw atom symbol with the contrast-correct colour.
            self.create_text(x, y, text=symbol, fill=label_color)

            # Draw charge if it exists and is non-zero. The charge sits
            # outside the atom marker on the white canvas background, so
            # it stays black regardless of the atom's fill colour.
            charge = getattr(self, '_atom_charges', {}).get(i, 0)
            if charge != 0:
                charge_x = x + 16
                charge_y = y - 16
                charge_text = f"{charge:+d}" if charge > 0 else str(charge)
                self.create_text(charge_x, charge_y, text=charge_text,
                                 font=('Arial', 8), fill='black')

    def _update_current_atom(self):
        """Update the current atom type"""
        self.current_atom = self.atom_var.get()
        # If in edit mode and an atom is selected, update its type
        if self.edit_mode and self.selected_item == 'atom':
            x, y, _ = self.atoms[self.selected_index]
            self.atoms[self.selected_index] = (x, y, self.current_atom)
            self._draw_canvas()
            self._update_smiles()
    
    def _update_current_bond(self):
        """Update the current bond type"""
        self.current_bond = self.bond_var.get()
        # If in edit mode and a bond is selected, update its type
        if self.edit_mode and self.selected_item == 'bond':
            start_idx, end_idx, _ = self.bonds[self.selected_index]
            self.bonds[self.selected_index] = (start_idx, end_idx, self.current_bond)
            self._draw_canvas()
            self._update_smiles()
    
    def clear_drawing(self):
        """Clear the drawing and reset state"""
        self.atoms = []
        self.bonds = []
        self.selected_atom = None
        self.drawing_bond = False
        self.start_atom = None
        self._draw_canvas()
        self._update_smiles()
    
    def _on_right_click(self, event):
        """Handle right mouse button click for deletion"""
        x, y = event.x, event.y
        
        # First check if we clicked on an atom
        clicked_atom = self._find_atom_near(x, y)
        if clicked_atom is not None:
            # Remove all bonds connected to this atom
            self.bonds = [(start, end, bond_type) for start, end, bond_type in self.bonds 
                         if start != clicked_atom and end != clicked_atom]
            
            # Remove the atom
            self.atoms.pop(clicked_atom)
            
            # Update indices in bonds list
            new_bonds = []
            for start, end, bond_type in self.bonds:
                new_start = start if start < clicked_atom else start - 1
                new_end = end if end < clicked_atom else end - 1
                new_bonds.append((new_start, new_end, bond_type))
            self.bonds = new_bonds
            
            # Update display
            self._draw_canvas()
            self._update_smiles()
            return
        
        # If no atom was clicked, check if we clicked on a bond
        for i, (start_idx, end_idx, _) in enumerate(self.bonds):
            start_x, start_y, _ = self.atoms[start_idx]
            end_x, end_y, _ = self.atoms[end_idx]
            
            # Check if click is near the bond line
            if self._point_near_line(x, y, start_x, start_y, end_x, end_y):
                # Remove the bond
                self.bonds.pop(i)
                self._draw_canvas()
                self._update_smiles()
                return
    
    def _point_near_line(self, px, py, x1, y1, x2, y2, threshold=5):
        """Check if a point is near a line segment"""
        # Calculate the distance from point to line segment
        line_length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        if line_length == 0:
            return False
        
        # Calculate the projection of the point onto the line
        t = max(0, min(1, ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / (line_length ** 2)))
        
        # Calculate the closest point on the line
        closest_x = x1 + t * (x2 - x1)
        closest_y = y1 + t * (y2 - y1)
        
        # Calculate the distance from the point to the closest point
        distance = ((px - closest_x) ** 2 + (py - closest_y) ** 2) ** 0.5
        
        return distance <= threshold

    def _canvas_dimensions(self):
        """Return usable canvas dimensions, even before Tk has fully mapped it."""
        width = self.winfo_width()
        height = self.winfo_height()
        if width <= 1:
            width = int(self.cget("width") or self.winfo_reqwidth() or 800)
        if height <= 1:
            height = int(self.cget("height") or self.winfo_reqheight() or 400)
        return width, height

    def _cleanup_molecule(self):
        """Recompute atom positions using RDKit's coordinate generation"""
        if not self.atoms:
            return
        
        try:
            # Create RDKit molecule
            mol = Chem.RWMol()
            
            # Add atoms
            atom_idx_map = {}
            for i, (_, _, symbol) in enumerate(self.atoms):
                if symbol == "X":
                    # Create a query atom for any halogen using SMARTS
                    atom = Chem.AtomFromSmarts("[#17,#35,#53]")  # Cl,Br,I
                elif symbol == "A":
                    # Create a query atom for any heavy atom using SMARTS
                    atom = Chem.AtomFromSmarts("[!#1]")  # Not H
                elif symbol == "*":
                    # Create a query atom for any atom using SMARTS
                    atom = Chem.AtomFromSmarts("*")
                else:
                    atom = Chem.Atom(symbol)
                atom_idx = mol.AddAtom(atom)
                atom_idx_map[i] = atom_idx
            
            # Add bonds
            for start_idx, end_idx, bond_type in self.bonds:
                mol.AddBond(atom_idx_map[start_idx], atom_idx_map[end_idx], 
                          Chem.BondType.values[bond_type])
            
            # Generate 2D coordinates
            AllChem.Compute2DCoords(mol)
            
            # Get canvas dimensions for centering
            width, height = self._canvas_dimensions()
            center_x = width / 2
            center_y = height / 2
            
            # Update atom positions
            conf = mol.GetConformer()
            new_atoms = []
            for i in range(mol.GetNumAtoms()):
                pos = conf.GetAtomPosition(i)
                # Scale and center the coordinates (RDKit coords are in Angstroms)
                x = center_x + pos.x * 30
                y = center_y - pos.y * 30  # Flip y-coordinate
                symbol = self.atoms[i][2]  # Keep the original symbol
                new_atoms.append((x, y, symbol))
            
            # Update atoms list
            self.atoms = new_atoms
            
            # Redraw the canvas
            self._draw_canvas()
            self._update_smiles()
            
        except Exception as e:
            print(f"Error cleaning up molecule: {e}")
            import traceback
            traceback.print_exc()

    def _update_smiles(self):
        """Convert the drawing to SMILES (or SMARTS if it contains query atoms)
        and update the bound ``StringVar``.
        """
        if not self.atoms:
            self.smiles_var.set("")
            return

        try:
            mol = Chem.RWMol()

            atom_idx_map = {}
            for i, (_, _, symbol) in enumerate(self.atoms):
                if symbol == "X":
                    atom = Chem.AtomFromSmarts("[#17,#35,#53]")  # F,Cl,Br,I
                elif symbol == "A":
                    atom = Chem.AtomFromSmarts("[!#1]")  # any heavy atom
                elif symbol == "*":
                    atom = Chem.AtomFromSmarts("*")  # any atom
                else:
                    atom = Chem.Atom(symbol)

                charge = getattr(self, "_atom_charges", {}).get(i, 0)
                if charge != 0:
                    atom.SetFormalCharge(charge)

                atom_idx = mol.AddAtom(atom)
                atom_idx_map[i] = atom_idx

            for start_idx, end_idx, bond_type in self.bonds:
                mol.AddBond(
                    atom_idx_map[start_idx],
                    atom_idx_map[end_idx],
                    Chem.BondType.values[bond_type],
                )

            # No need to Kekulize here -- mol_to_storage_string runs
            # perceive_aromaticity itself, which would just undo any explicit
            # Kekulization we did. Aromaticity perception turns drawn benzene
            # rings into ``c1ccccc1`` (or aromatic-bond SMARTS like
            # ``[#6]1:[#6]:...:1-*`` when wildcards are present), which is
            # what substructure search expects.
            text = mol_to_storage_string(mol)
            if text is None:
                logger.warning("Generated molecule could not be serialised")
                self.smiles_var.set("")
                return

            self.smiles_var.set(text)
        except Exception:
            logger.exception("Error converting drawing to SMILES/SMARTS")
            self.smiles_var.set("")

    def create_ring_toolbar(self, parent):
        """Create a toolbar with ring template buttons"""
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill='x', pady=(0, 5))
        
        ttk.Label(toolbar, text="Rings:").pack(side='left', padx=5)
        
        # Add ring template buttons.
        # Pyrrole's nitrogen needs an explicit H to satisfy aromaticity;
        # ``n1cccc1`` does not parse with RDKit. Furan/Thiophene parse either
        # way, but the canonical aromatic forms below are the ones RDKit emits
        # so round-tripping is stable.
        rings = [
            ("Benzene", "c1ccccc1", "Add benzene (aromatic 6-ring, C6H6)."),
            ("Cyclopentane", "C1CCCC1", "Add cyclopentane (saturated 5-ring)."),
            ("Cyclohexane", "C1CCCCC1", "Add cyclohexane (saturated 6-ring)."),
            ("Pyrrole", "[nH]1cccc1", "Add pyrrole (aromatic 5-ring with NH)."),
            ("Furan", "c1ccoc1", "Add furan (aromatic 5-ring with O)."),
            ("Thiophene", "c1ccsc1", "Add thiophene (aromatic 5-ring with S)."),
        ]

        for name, smiles, hint in rings:
            btn = ttk.Button(toolbar, text=name,
                             command=lambda s=smiles: self._add_ring_template(s))
            btn.pack(side='left', padx=2)
            Tooltip(btn, hint)

        return toolbar
    
    def _add_ring_template(self, smiles):
        """Add a ring template at the center of the canvas"""
        try:
            mol = Chem.MolFromSmiles(smiles)
            if not mol:
                logger.warning("Ring template %r could not be parsed by RDKit", smiles)
                messagebox.showwarning(
                    "Ring template",
                    f"Could not parse ring template SMILES: {smiles!r}",
                )
                return

            AllChem.Compute2DCoords(mol)
            try:
                Chem.Kekulize(mol, clearAromaticFlags=True)
            except Exception:
                # Kekulize raises on query atoms / unusual aromatic systems.
                # The drawing still works fine using aromatic bond orders.
                pass

            width = self.winfo_width()
            height = self.winfo_height()
            center_x = width / 2
            center_y = height / 2

            if not self.atoms:
                self.clear_drawing()

            start_idx = len(self.atoms)

            conf = mol.GetConformer()
            for i in range(mol.GetNumAtoms()):
                pos = conf.GetAtomPosition(i)
                x = center_x + pos.x * 30
                y = center_y - pos.y * 30  # canvas y grows downwards
                atom = mol.GetAtomWithIdx(i)
                symbol = atom.GetSymbol()
                self.atoms.append((x, y, symbol))

            for bond in mol.GetBonds():
                begin_idx = bond.GetBeginAtomIdx() + start_idx
                end_idx = bond.GetEndAtomIdx() + start_idx
                # ``int(GetBondTypeAsDouble())`` truncates aromatic bonds
                # (1.5) to single (1); ``round`` keeps double bonds intact
                # if Kekulize ever fails to apply to a particular bond.
                bond_type = max(1, round(bond.GetBondTypeAsDouble()))
                self.bonds.append((begin_idx, end_idx, bond_type))

            self._draw_canvas()
            self._update_smiles()

            # Re-run the layout cleanup after inserting a ring so the new
            # fragment is laid out together with whatever is already on the
            # canvas instead of being overlaid on top of existing atoms.
            try:
                self.after(0, self._cleanup_molecule)
            except tk.TclError:
                # Canvas already torn down – nothing to schedule.
                pass

        except Exception:
            logger.exception("Error adding ring template %r", smiles)
            messagebox.showerror(
                "Ring template",
                f"Unexpected error while adding ring template {smiles!r}.",
            )

    def _find_atom_near(self, x, y, threshold=10):
        """Find atom index near given coordinates"""
        for i, (ax, ay, _) in enumerate(self.atoms):
            if abs(x - ax) <= threshold and abs(y - ay) <= threshold:
                return i
        return None

    def _update_additional_atom(self, atom_type):
        """Update the current atom type when an additional element is selected"""
        self.atom_var.set(atom_type)
        self._update_current_atom()

    def _on_key_press(self, event):
        """Handle keyboard shortcuts"""
        if event.char.lower() == 'd':
            self.mode_var.set("draw")
            self._update_mode()
        elif event.char.lower() == 'e':
            self.mode_var.set("edit")
            self._update_mode()

class MoleculeEditorWindow(tk.Toplevel):
    def __init__(self, parent, smiles_var):
        super().__init__(parent)
        self.title("Molecule Editor")
        self.geometry("1200x600")  # Increased width
        
        # Create main container
        main_frame = ttk.Frame(self)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Create the drawing canvas
        self.mol_canvas = MoleculeDrawingCanvas(main_frame, smiles_var,
                                              bg='white', bd=2, relief='solid',
                                              highlightthickness=2, highlightbackground='blue',
                                              width=800, height=400)  # Increased width
        
        # Bind keyboard shortcuts to the window
        self.bind("<Key>", self._on_key_press)
        
        # Initialize with the existing molecule (if any). Prefer SMILES over
        # SMARTS so we don't misread lowercase aromatics in normal molecules.
        needs_initial_cleanup = False
        smiles = smiles_var.get().strip()
        if smiles != smiles_var.get():
            smiles_var.set(smiles)
        if smiles:
            try:
                mol, _kind = parse_molecule(smiles)
                if mol is not None:
                    cleaned = mol_to_storage_string(mol)
                    if cleaned is not None:
                        smiles = cleaned
                        smiles_var.set(cleaned)

                    AllChem.Compute2DCoords(mol)

                    # Kekulize before reading bond orders. The drawing canvas
                    # only supports integer bond types (1=single, 2=double,
                    # 3=triple); aromatic bonds report ``GetBondTypeAsDouble()
                    # == 1.5``, and ``int(1.5) == 1`` would silently turn every
                    # benzene ring into cyclohexane. Failure to kekulize is
                    # tolerated for query molecules where it can legitimately
                    # raise.
                    try:
                        Chem.Kekulize(mol, clearAromaticFlags=True)
                    except Exception:
                        logger.debug(
                            "Could not kekulize %r when reopening editor", smiles
                        )

                    width, height = self.mol_canvas._canvas_dimensions()
                    center_x = width / 2
                    center_y = height / 2

                    conf = mol.GetConformer()
                    for i in range(mol.GetNumAtoms()):
                        pos = conf.GetAtomPosition(i)
                        x = center_x + pos.x * 30
                        y = center_y - pos.y * 30
                        atom = mol.GetAtomWithIdx(i)
                        symbol = atom.GetSymbol()
                        self.mol_canvas.atoms.append((x, y, symbol))

                    for bond in mol.GetBonds():
                        begin_idx = bond.GetBeginAtomIdx()
                        end_idx = bond.GetEndAtomIdx()
                        # Round defensively in case kekulization didn't apply
                        # to a particular bond (e.g. mixed aromatic/non-arom
                        # systems): we'd rather end up with double bonds in
                        # an aromatic ring than silently dropping them all
                        # to single.
                        bond_type = max(1, round(bond.GetBondTypeAsDouble()))
                        self.mol_canvas.bonds.append(
                            (begin_idx, end_idx, bond_type)
                        )

                    needs_initial_cleanup = True
                else:
                    logger.warning("Existing value %r is neither valid SMILES nor SMARTS", smiles)
            except Exception:
                logger.exception("Error initializing molecule editor with %r", smiles)
        
        # Add a close button
        close_btn = ttk.Button(main_frame, text="Close", command=self.destroy)
        close_btn.pack(pady=5)
        Tooltip(close_btn, "Close the editor and keep the current SMILES.")
        
        # Make window modal
        self.transient(parent)
        self.grab_set()
        
        # Center the window
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')
        if needs_initial_cleanup:
            self.after(50, self.mol_canvas._cleanup_molecule)

    def _on_key_press(self, event):
        """Handle keyboard shortcuts"""
        if event.char.lower() == 'd':
            self.mol_canvas.mode_var.set("draw")
            self.mol_canvas._update_mode()
        elif event.char.lower() == 'e':
            self.mol_canvas.mode_var.set("edit")
            self.mol_canvas._update_mode()
