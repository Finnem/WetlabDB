"""Treeview that renders a small molecule image in each row."""

from __future__ import annotations

import io
import logging

from tkinter import ttk
from PIL import Image, ImageTk

from wetlabdb.chem import parse_smiles, render_to_png_bytes

logger = logging.getLogger(__name__)

class MoleculeTreeview(ttk.Treeview):
    def __init__(self, master, **kwargs):
        # Use original columns without adding Structure
        if 'columns' in kwargs:
            self.original_columns = kwargs['columns']
        kwargs['show'] = 'tree headings'  # Keep tree to show option for images
        super().__init__(master, **kwargs)
        
        self.molecule_images = {}
        self.query_mol = None  # Store the query molecule for highlighting
        self.bind('<<TreeviewSelect>>', self._on_select)
        self.bind('<Configure>', self._on_configure)
        self.bind('<Visibility>', self._on_visibility)
        
        # Configure the tree column for images
        self.heading('#0', text='Structure')
        self.column('#0', width=200, anchor='center', stretch=False)  # Increased from 150 to 200
        
        # Store the index of the SMILES column
        self.smiles_index = self.original_columns.index('SMILES')
    
    def set_query_mol(self, mol):
        """Set the query molecule for highlighting"""
        self.query_mol = mol
        self._update_images()  # Update all images with new highlighting
    
    def _on_select(self, event):
        """Handle selection event"""
        pass
    
    def _on_configure(self, event):
        """Handle window resize"""
        self._update_images()
    
    def _on_visibility(self, event):
        """Handle visibility changes"""
        self._update_images()
    
    def _update_images(self):
        """Update all visible molecule images"""
        for item in self.get_children():
            self._update_item_image(item)
    
    def _update_item_image(self, item):
        """Update the image for a specific item."""
        values = self.item(item)["values"]
        if not values or len(values) <= self.smiles_index:
            return
        smiles = values[self.smiles_index]
        if not smiles:
            return

        highlight_atoms = None
        if self.query_mol is not None:
            mol = parse_smiles(smiles)
            if mol is not None:
                try:
                    match = mol.GetSubstructMatch(self.query_mol)
                    if match:
                        highlight_atoms = list(match)
                except Exception:
                    logger.debug("Substructure match failed for %r", smiles, exc_info=True)

        png = render_to_png_bytes(
            smiles,
            width=150,
            height=150,
            highlight_atoms=highlight_atoms,
        )
        if png is None:
            logger.debug("Treeview could not render %r", smiles)
            return

        try:
            img = Image.open(io.BytesIO(png))
            photo = ImageTk.PhotoImage(img)
            self.molecule_images[smiles] = photo
            self.item(item, image=photo)
        except Exception:
            logger.exception("Treeview could not display %r", smiles)
    
    def insert(self, parent, index, **kwargs):
        """Override insert to handle molecule images"""
        item = super().insert(parent, index, **kwargs)
        self._update_item_image(item)
        return item
