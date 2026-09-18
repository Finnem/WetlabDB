"""Tiny Tk Canvas widget that renders a single molecule from SMILES."""

from __future__ import annotations

import io
import logging

import tkinter as tk
from PIL import Image, ImageTk

from wetlabdb.chem import render_to_png_bytes

logger = logging.getLogger(__name__)


class MoleculeCell(tk.Canvas):
    def __init__(self, parent, width=100, height=100, **kwargs):
        super().__init__(parent, width=width, height=height, **kwargs)
        self.configure(bg="black", highlightthickness=0)
        self._width = width
        self._height = height
        self.image = None

    def set_molecule(self, smiles):
        if not smiles:
            self.delete("all")
            self.image = None
            return

        png = render_to_png_bytes(
            smiles,
            width=self._width,
            height=self._height,
            background=(0.0, 0.0, 0.0, 1.0),
        )
        if png is None:
            logger.debug("MoleculeCell could not render %r", smiles)
            self.delete("all")
            self.image = None
            return

        try:
            img = Image.open(io.BytesIO(png))
            photo = ImageTk.PhotoImage(img)
            self.delete("all")
            self.create_image(self._width // 2, self._height // 2, image=photo)
            self.image = photo  # keep reference so Tk doesn't GC the image
        except Exception:
            logger.exception("MoleculeCell could not display %r", smiles)
            self.delete("all")
            self.image = None
