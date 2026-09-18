"""Molecular search window (similarity & substructure)."""

from __future__ import annotations

import io
import logging

import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk

from wetlabdb.chem import (
    DEFAULT_METRIC,
    METRIC_DEFAULT_CUTOFFS,
    METRIC_DESCRIPTIONS,
    SIMILARITY_METRICS,
    enumerate_molecules_from_smarts,
    parse_molecule,
    render_to_png_bytes,
)
from wetlabdb.ui.molecule_editor import MoleculeEditorWindow, Tooltip
from wetlabdb.ui.molecule_treeview import MoleculeTreeview

logger = logging.getLogger(__name__)


def _render_smiles_on_canvas(canvas, smiles, *, width=None, height=None):
    """Render ``smiles`` (SMILES or SMARTS) onto a Tk Canvas, centred.

    Returns ``True`` on success, ``False`` on parse / draw failure (in which
    case the caller is responsible for showing a fallback message).
    """
    w = width if width is not None else canvas.winfo_width()
    h = height if height is not None else canvas.winfo_height()
    if w <= 1 or h <= 1:
        return False

    png = render_to_png_bytes(smiles, width=w, height=h)
    if png is None:
        return False
    try:
        img = Image.open(io.BytesIO(png))
        photo = ImageTk.PhotoImage(img)
    except Exception:
        logger.exception("Could not decode rendered PNG for %r", smiles)
        return False

    canvas.delete("all")
    canvas.create_image(w // 2, h // 2, image=photo, anchor="center")
    canvas.image = photo  # keep reference so Tk doesn't GC the image
    return True

class MolecularSearchWindow(tk.Toplevel):
    def __init__(self, parent, collection):
        super().__init__(parent)
        self.title("Molecular Search")
        self.geometry("1100x900")  # Increased height from 800 to 900
        
        self.collection = collection
        self.query_mol = None
        self.selected_smiles = None  # Track currently selected molecule's SMILES
        
        # Create main container
        main_frame = ttk.Frame(self)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Input frame at top
        input_frame = ttk.Frame(main_frame)
        input_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(input_frame, text="SMILES:").pack(side='left', padx=5)
        self.smiles_var = tk.StringVar()
        self.smiles_entry = ttk.Entry(input_frame, textvariable=self.smiles_var, width=50)
        self.smiles_entry.pack(side='left', padx=5)
        
        # Add Edit button next to SMILES entry
        ttk.Button(input_frame, text="Edit Molecule", 
                  command=self._open_molecule_editor).pack(side='left', padx=5)
        
        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=(0, 10))
        
        # Similarity metric selector. Values come from the central
        # ``SIMILARITY_METRICS`` registry so adding a new metric there is
        # automatically reflected in this dropdown without UI churn.
        # Built before the cutoff so a "moderately similar" default for the
        # active metric can seed the slider on startup.
        metric_frame = ttk.Frame(button_frame)
        metric_frame.pack(side='left', padx=10)
        ttk.Label(metric_frame, text="Metric:").pack(side='left', padx=5)
        self.metric_var = tk.StringVar(value=DEFAULT_METRIC)
        self.metric_combo = ttk.Combobox(
            metric_frame,
            textvariable=self.metric_var,
            values=list(SIMILARITY_METRICS.keys()),
            state='readonly',
            width=14,
        )
        self.metric_combo.pack(side='left', padx=5)
        # Dynamic tooltip: re-resolves on every hover so it always reflects
        # the currently-selected metric, even after the user changes it.
        Tooltip(
            self.metric_combo,
            lambda: METRIC_DESCRIPTIONS.get(self.metric_var.get(), ""),
            delay_ms=250,
        )
        self.metric_combo.bind(
            '<<ComboboxSelected>>', self._on_metric_changed
        )

        # Similarity cutoff frame -- seeded with the default cutoff for the
        # active metric so opening the window already shows a useful value.
        cutoff_frame = ttk.Frame(button_frame)
        cutoff_frame.pack(side='left', padx=20)
        ttk.Label(cutoff_frame, text="Similarity Cutoff:").pack(side='left', padx=5)
        initial_cutoff = METRIC_DEFAULT_CUTOFFS.get(DEFAULT_METRIC, 0.7)
        self.cutoff_var = tk.DoubleVar(value=initial_cutoff)
        # Several metrics (notably McConnaughey) can produce negative scores,
        # so allow the cutoff to go below zero. The slider stays in [0, 1]
        # for the bulk of metrics that live in that range; users who want
        # full negative coverage can use the "Sort by Similarity" button.
        self.cutoff_scale = ttk.Scale(cutoff_frame, from_=-1.0, to=1.0,
                                    variable=self.cutoff_var, orient='horizontal',
                                    length=150)
        self.cutoff_scale.pack(side='left', padx=5)
        self.cutoff_label = ttk.Label(cutoff_frame, text=f"{initial_cutoff:.2f}")
        self.cutoff_label.pack(side='left', padx=5)
        Tooltip(
            self.cutoff_scale,
            "Minimum similarity for a compound to appear in the results.\n"
            "Default value is set per metric so it stays meaningful when\n"
            "you switch between Tanimoto, Dice, McConnaughey, etc.",
            delay_ms=400,
        )

        # Search buttons
        ttk.Button(button_frame, text="Similarity Search",
                  command=self.perform_similarity_search).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Sort by Similarity",
                  command=self.perform_similarity_sort).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Substructure Search",
                  command=self.perform_substructure_search).pack(side='left', padx=5)
        
        # Create a frame for the table and molecule display
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill='both', expand=True)
        
        # Create a paned window for resizable sections
        self.paned = ttk.PanedWindow(content_frame, orient='vertical')
        self.paned.pack(fill='both', expand=True)
        
        # Results table in the middle
        table_frame = ttk.Frame(self.paned)
        self.create_results_table(table_frame)
        self.paned.add(table_frame, weight=2)  # Reduced from 3 to 2
        
        # Create a frame for the molecule display
        self.mol_display_frame = tk.Frame(self.paned, bg='#f0f0f0', bd=2, relief='solid')
        
        # Add a title label
        title_label = tk.Label(self.mol_display_frame, text="Molecule Display", 
                             font=('Arial', 12, 'bold'), bg='#f0f0f0')
        title_label.pack(pady=(5,0))
        
        # Create the molecule display canvas
        self.mol_canvas = tk.Canvas(self.mol_display_frame, bg='white', 
                                  bd=2, relief='solid',
                                  highlightthickness=2, highlightbackground='blue',
                                  width=400, height=400)  # Increased height from 300 to 400
        self.mol_canvas.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Add molecule display to paned window
        self.paned.add(self.mol_display_frame, weight=2)  # Increased from 1 to 2
        
        # Force the frame to be visible
        self.mol_display_frame.lift()
        
        # Update the window
        self.update_idletasks()
        self.update()
        
        # Bind SMILES entry to molecule display
        self.cutoff_var.trace_add('write', self._update_cutoff_label)
        self.smiles_var.trace_add('write', self._on_smiles_change)
    
    def _open_molecule_editor(self):
        """Open the molecule editor in a new window"""
        MoleculeEditorWindow(self, self.smiles_var)

    # ------------------------------------------------------------------
    # Modal dialog helpers
    # ------------------------------------------------------------------
    # Tkinter's ``messagebox`` defaults its ``parent`` to the application
    # root window, which means once a dialog is dismissed the *root*
    # window receives focus -- not this Toplevel. That's jarring during
    # a search session, so route every popup through these wrappers so
    # the dialog is parented to the search window and we can re-grab
    # focus once the user dismisses it.
    def _info(self, title: str, message: str) -> None:
        messagebox.showinfo(title, message, parent=self)
        self._reclaim_focus()

    def _warn(self, title: str, message: str) -> None:
        messagebox.showwarning(title, message, parent=self)
        self._reclaim_focus()

    def _error(self, title: str, message: str) -> None:
        messagebox.showerror(title, message, parent=self)
        self._reclaim_focus()

    def _reclaim_focus(self) -> None:
        """Pull focus back onto the search window after a modal dialog."""
        try:
            if not self.winfo_exists():
                return
            self.lift()
            self.focus_force()
            # If the SMILES entry exists and held focus before the dialog,
            # restoring focus there is the most useful spot to land.
            if hasattr(self, "smiles_entry"):
                self.smiles_entry.focus_set()
        except tk.TclError:
            pass
    
    def _on_smiles_focus(self, event):
        """Update the molecule display when SMILES entry is focused"""
        smiles = self.smiles_var.get()
        if smiles:
            # Set as selected molecule
            self.selected_smiles = smiles
            self._on_smiles_change()
    
    def create_results_table(self, parent):
        # Create Treeview with Structure column
        columns = ['Name', 'SMILES', 'CAS Nr', 'Storage Location', 'Similarity']
        self.results_tree = MoleculeTreeview(parent, columns=columns, show='headings', height=5)  # Added height=5 to limit visible rows
        
        # Configure style for molecular search table (more compact)
        style = ttk.Style()
        style.configure("Search.Treeview", rowheight=160)  # Increased from 80 to 160 for larger images
        self.results_tree.configure(style="Search.Treeview")
        
        # Configure columns
        for col in columns:
            self.results_tree.heading(col, text=col)
            if col == 'SMILES':
                self.results_tree.column(col, width=200)
            elif col == 'Similarity':
                self.results_tree.column(col, width=100)
            else:
                self.results_tree.column(col, width=100)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(parent, orient='vertical', command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=scrollbar.set)
        
        # Add download button
        download_btn = ttk.Button(parent, text="Download Results", command=self.download_search_results)
        download_btn.pack(side='top', pady=5)
        
        # Pack table and scrollbar
        self.results_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Bind selection event
        self.results_tree.bind('<<TreeviewSelect>>', self.on_result_selected)
    
    def _update_cutoff_label(self, *args):
        """Update the cutoff label with the current value"""
        self.cutoff_label.configure(text=f"{self.cutoff_var.get():.2f}")

    def _on_metric_changed(self, _event=None):
        """Reset the cutoff slider to the new metric's default.

        Different metrics live on very different numeric scales (Russel
        is in single-digit percent, Rogot-Goldberg is close to 1 by
        construction, McConnaughey can go negative) so a cutoff that
        means "moderately similar" under Tanimoto is meaningless under
        Russel. Resetting to a per-metric default keeps the slider's
        qualitative meaning stable across switches.
        """
        metric = self.metric_var.get()
        default = METRIC_DEFAULT_CUTOFFS.get(metric)
        if default is None:
            return
        self.cutoff_var.set(default)
    
    def _on_smiles_change(self, *args):
        smiles = self.smiles_var.get()
        if not smiles:
            self._clear_canvas("Enter SMARTS to display molecule", colour="gray")
            self.query_mol = None
            self.results_tree.set_query_mol(None)
            self.selected_smiles = None
            return

        mol, _kind = parse_molecule(smiles)
        if mol is None:
            self._clear_canvas("Invalid SMILES / SMARTS", colour="red")
            self.query_mol = None
            self.results_tree.set_query_mol(None)
            self.selected_smiles = None
            return

        self.query_mol = mol
        self.results_tree.set_query_mol(mol)
        self.selected_smiles = smiles

        if not _render_smiles_on_canvas(self.mol_canvas, smiles):
            self._clear_canvas(f"Pattern: {smiles}", colour="blue")

    def _clear_canvas(self, message, *, colour="gray", subtitle=None):
        """Reset ``self.mol_canvas`` to a centred text message."""
        self.mol_canvas.delete("all")
        width = self.mol_canvas.winfo_width()
        height = self.mol_canvas.winfo_height()
        if width <= 1 or height <= 1:
            return
        cx, cy = width // 2, height // 2
        self.mol_canvas.create_text(cx, cy, text=message, fill=colour, font=("Arial", 12))
        if subtitle:
            self.mol_canvas.create_text(cx, cy + 20, text=subtitle, fill="blue", font=("Arial", 10))
    
    def perform_similarity_search(self):
        """Filter compounds by similarity >= the slider cutoff."""
        cutoff = self.cutoff_var.get()
        self._run_similarity_query(
            cutoff=cutoff,
            empty_message=(
                f"No molecules found with {self.metric_var.get()} similarity "
                f">= {cutoff:.2f}"
            ),
        )

    def perform_similarity_sort(self):
        """Sort *all* compounds by similarity to the query (no threshold).

        This is the "I just want to see the most-similar compounds" mode --
        the cutoff slider is ignored so even very dissimilar hits show up at
        the bottom of the list. We pass a deeply-negative cutoff so metrics
        that can produce negative scores (e.g. McConnaughey, range [-1, 1])
        still return every comparable compound.
        """
        self._run_similarity_query(
            cutoff=-2.0,
            empty_message=(
                "No compounds with valid SMILES were found in this collection."
            ),
        )

    def _run_similarity_query(self, *, cutoff: float, empty_message: str):
        """Shared core for similarity search / sort.

        Both entry points only differ in the cutoff they pass to
        :func:`similarity_search` and the wording of the "no results" dialog,
        so the parsing, table population and error handling live here.
        """
        from wetlabdb.chem import (
            enumerate_molecules_from_smarts as _enum,
            looks_like_smarts,
            parse_smiles,
            similarity_search,
        )

        smiles = self.smiles_var.get()
        if not smiles:
            self._warn("Warning", "Please enter a SMILES/SMARTS string")
            return

        metric = self.metric_var.get() or DEFAULT_METRIC

        try:
            query_mol = parse_smiles(smiles)
            if query_mol is not None:
                query_mols = [query_mol]
            elif looks_like_smarts(smiles):
                query_mols = _enum(smiles)
                if not query_mols:
                    self._error(
                        "Error",
                        "Could not generate valid molecules from SMARTS pattern",
                    )
                    return
            else:
                self._error("Error", "Invalid SMILES string")
                return

            self.results_tree.delete(*self.results_tree.get_children())
            hits = similarity_search(
                self.collection.find(),
                query_mols,
                cutoff=cutoff,
                metric=metric,
            )

            for hit in hits:
                doc = hit.document
                values = [
                    doc.get('Name', ''),
                    doc.get('SMILES', ''),
                    doc.get('CAS Nr', ''),
                    doc.get('Storage Location', ''),
                    f"{hit.similarity:.3f}",
                ]
                self.results_tree.insert('', 'end', values=values)

            if not hits:
                self._info("Info", empty_message)

        except Exception as e:
            self._error(
                "Error", f"Error performing similarity search: {str(e)}"
            )

    def perform_substructure_search(self):
        from wetlabdb.chem import parse_smarts_for_search, substructure_search

        smiles = self.smiles_var.get()
        if not smiles:
            self._warn("Warning", "Please enter a SMILES string")
            return

        try:
            # Use the search-aware parser so Kekulé-form SMARTS from the 2D
            # editor (or legacy data) match aromatic SMILES targets. The same
            # aromatized query is also used for atom highlighting in the
            # results tree, so the two paths agree on what got matched.
            query_mol = parse_smarts_for_search(smiles)
            if not query_mol:
                self._error("Error", "Invalid SMILES/SMARTS string")
                return

            self.results_tree.set_query_mol(query_mol)
            self.results_tree.delete(*self.results_tree.get_children())

            hits = substructure_search(self.collection.find(), smiles)

            for hit in hits:
                doc = hit.document
                values = [
                    doc.get('Name', ''),
                    doc.get('SMILES', ''),
                    doc.get('CAS Nr', ''),
                    doc.get('Storage Location', ''),
                    '1.000',
                ]
                self.results_tree.insert('', 'end', values=values)

            if not hits:
                self._info("Info", "No substructure matches found")

        except Exception as e:
            # Show error message but don't close the window
            self._error(
                "Error", f"Error performing substructure search: {str(e)}"
            )
            # Reset search state to ensure window stays open
            self.results_tree.delete(*self.results_tree.get_children())
            if hasattr(self, 'query_mol') and self.query_mol:
                # Keep the query molecule displayed if it's valid
                pass
            else:
                # Clear everything if query isn't valid
                self.mol_canvas.delete('all')
                center_x = self.mol_canvas.winfo_width() // 2
                center_y = self.mol_canvas.winfo_height() // 2
                self.mol_canvas.create_text(center_x, center_y, text="Error with search query",
                                         fill='red', font=('Arial', 12))
    
    def on_result_selected(self, event):
        selection = self.results_tree.selection()
        if not selection:
            return

        smiles = self.results_tree.item(selection[0])["values"][1]
        if not smiles:
            return

        if _render_smiles_on_canvas(self.mol_canvas, smiles):
            self.selected_smiles = smiles
        else:
            logger.debug("on_result_selected could not render %r", smiles)
            self.mol_canvas.delete("all")
            self.selected_smiles = None

    def _on_canvas_resize(self, event):
        """Handle canvas resize events"""
        width = event.width
        height = event.height

        # Use the selected molecule's SMILES if available, otherwise the query.
        smiles_to_draw = self.selected_smiles or self.smiles_var.get() or None

        if not smiles_to_draw:
            self.mol_canvas.delete("all")
            self.mol_canvas.create_text(
                width // 2,
                height // 2,
                text="Enter SMILES to display molecule",
                fill="gray",
                font=("Arial", 12),
            )
            return

        if not _render_smiles_on_canvas(
            self.mol_canvas, smiles_to_draw, width=width, height=height
        ):
            self.mol_canvas.delete("all")
            cx, cy = width // 2, height // 2
            self.mol_canvas.create_text(
                cx, cy, text="Cannot display structure", fill="red", font=("Arial", 12)
            )
            self.mol_canvas.create_text(
                cx,
                cy + 20,
                text=f"Pattern: {smiles_to_draw}",
                fill="blue",
                font=("Arial", 10),
            )

    def download_search_results(self):
        """Download the search results as a CSV file"""
        if not self.results_tree.get_children():
            self._warn("Warning", "No search results to export")
            return

        # Get file path from user. ``parent=self`` keeps the file dialog
        # docked to the search window so dismissing it returns focus here
        # rather than to the main app.
        file_path = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="search_results.csv"
        )

        if not file_path:
            self._reclaim_focus()
            return

        try:
            items = self.results_tree.get_children()
            headers = ['Name', 'SMILES', 'CAS Nr', 'Storage Location', 'Similarity']

            data = []
            for item in items:
                values = self.results_tree.item(item)['values']
                data.append(values)

            df = pd.DataFrame(data, columns=headers)
            df.to_csv(file_path, index=False)

            self._info(
                "Success",
                f"Search results exported successfully to {file_path}",
            )

        except Exception as e:
            self._error("Error", f"Error exporting search results: {str(e)}")
