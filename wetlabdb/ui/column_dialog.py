"""Auto-generated during the Phase 5 refactor (one class per module)."""

from __future__ import annotations

import base64
import io
import json
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
from wetlabdb.chem import enumerate_molecules_from_smarts
from wetlabdb.config import AppConfig, CONFIG_FILENAME
class ColumnSelectionDialog(tk.Toplevel):
    def __init__(self, parent, columns):
        super().__init__(parent)
        self.title("Select Columns")
        self.geometry("600x500")  # Increased width from 400 to 600
        
        # Make dialog modal
        self.transient(parent)
        self.grab_set()
        
        # Store columns
        self.columns = columns
        self.result = None
        
        # Create main frame
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill='both', expand=True)
        
        # Identifier selection
        ttk.Label(main_frame, text="Select Identifier Column:").pack(anchor='w', pady=(0, 5))
        self.identifier_var = tk.StringVar()
        identifier_frame = ttk.Frame(main_frame)
        identifier_frame.pack(fill='x', pady=(0, 10))
        
        # Only allow CAS Nr, Name, or SMILES as identifiers
        valid_identifiers = ['CAS Nr', 'Name', 'SMILES']
        for col in valid_identifiers:
            if col in columns:
                ttk.Radiobutton(identifier_frame, text=col, value=col, 
                              variable=self.identifier_var).pack(side='left', padx=5)
        
        # Data columns selection
        ttk.Label(main_frame, text="Select Data Columns:").pack(anchor='w', pady=(0, 5))
        
        # Create canvas and scrollbar for data columns
        canvas = tk.Canvas(main_frame)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        
        # Create frame for checkboxes
        checkbox_frame = ttk.Frame(canvas)
        
        # Configure canvas
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Pack scrollbar and canvas
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        
        # Create window in canvas for checkbox frame
        canvas_frame = canvas.create_window((0, 0), window=checkbox_frame, anchor="nw")
        
        # Create variables for checkboxes
        self.column_vars = {}
        for col in sorted(columns):
            # Show all columns except the selected identifier in data selection
            var = tk.BooleanVar(value=True)  # Default to selected
            self.column_vars[col] = var
            ttk.Checkbutton(checkbox_frame, text=col, variable=var).pack(anchor='w', pady=2)
        
        # Configure canvas scrolling
        def configure_scroll_region(event):
            try:
                if canvas.winfo_exists():
                    # Update the scroll region to encompass the form
                    canvas.configure(scrollregion=canvas.bbox('all'))
                    # Update the canvas window width to match the canvas width
                    canvas.itemconfig(canvas_frame, width=canvas.winfo_width())
                    
                    # Check if scrollbar is needed
                    check_scrollbar_needed()
            except (tk.TclError, RuntimeError):
                # Widget doesn't exist anymore or was destroyed
                pass
        
        def configure_canvas_width(event):
            canvas.itemconfig(canvas_frame, width=event.width)
        
        checkbox_frame.bind("<Configure>", configure_scroll_region)
        canvas.bind("<Configure>", configure_canvas_width)
        
        # Add buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill='x', pady=10)
        ttk.Button(btn_frame, text="Import", command=self._on_import).pack(side='right', padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self._on_cancel).pack(side='right', padx=5)
        
        # Center the dialog
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')
    
    def _on_import(self):
        identifier = self.identifier_var.get()
        if not identifier:
            messagebox.showerror("Error", "Please select an identifier column")
            return
        
        # Get all selected columns except the identifier
        data_columns = [col for col, var in self.column_vars.items() if var.get() and col != identifier]
        if not data_columns:
            messagebox.showerror("Error", "Please select at least one data column")
            return
        
        self.result = (identifier, data_columns)
        self.destroy()
    
    def _on_cancel(self):
        self.result = None
        self.destroy()
