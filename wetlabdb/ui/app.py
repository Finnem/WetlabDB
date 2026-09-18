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
    canonicalize_smiles,
    enumerate_molecules_from_smarts,
    render_to_png_bytes,
)
from wetlabdb.config import AppConfig, CONFIG_FILENAME

logger = logging.getLogger(__name__)
from wetlabdb.services import (
    CompoundService,
    SearchService,
    export_csv as _export_csv,
    import_csv as _import_csv,
)
from wetlabdb.ui.column_dialog import ColumnSelectionDialog
from wetlabdb.ui.json_form import JSONForm, compound_form
from wetlabdb.ui.login_dialog import LoginDialog
from wetlabdb.ui.molecule_treeview import MoleculeTreeview
from wetlabdb.ui.search_window import MolecularSearchWindow

class MongoBrowser(tk.Tk):
    def __init__(self):
        super().__init__()
        
        # Persisted application config -- lives behind a typed AppConfig dataclass
        # but is mirrored to ``self.config`` (a plain dict) for backwards
        # compatibility with the rest of this monolith.
        self.app_config = AppConfig.load()
        self.config = self.app_config.to_dict()

        self.current_user = None

        self.last_width = None
        self.last_height = None
        self.resize_after_id = None
        self.bind('<Configure>', self._on_window_configure)
        
        self.initializing = True
        self.title("MongoDB Browser")
        self.geometry("1200x800")
        
        # Default columns
        self.default_columns = ['Name', 'SMILES', 'CAS Nr', 'Storage Location']
        self.visible_columns = self.default_columns.copy()
        self.all_columns = set(self.default_columns)
        
        # Flag to prevent premature saving
        self.initializing = True
        
        # Create main container
        self.main_container = ttk.PanedWindow(self, orient='horizontal')
        self.main_container.pack(fill='both', expand=True)
        
        # Create left panel for database/collection selection
        self.left_panel = ttk.Frame(self.main_container)
        self.main_container.add(self.left_panel, weight=1)
        
        # Create right panel for document display
        self.right_panel = ttk.Frame(self.main_container)
        self.main_container.add(self.right_panel, weight=3)

        # Persistent left/right split ratio. The right-hand viewer (molecule
        # preview + properties) is intentionally limited to ~30% of the window
        # width so the compound table dominates and stays readable; once the
        # user drags the sash we remember the new ratio and re-apply it on
        # every resize so the split doesn't drift as the window grows or
        # shrinks. ``_main_sash_ratio`` is the *left* panel's share, so the
        # default 0.70 leaves 0.30 for the right viewer.
        DEFAULT_MAIN_SASH_RATIO = 0.70
        try:
            stored_ratio = float(self.config.get('main_sash_ratio', DEFAULT_MAIN_SASH_RATIO))
        except (TypeError, ValueError):
            stored_ratio = DEFAULT_MAIN_SASH_RATIO
        self._main_sash_ratio = min(0.9, max(0.1, stored_ratio))
        self._main_sash_applying = False
        self._main_sash_save_after_id = None
        self.main_container.bind('<Configure>', self._on_main_container_configure, add='+')
        self.main_container.bind('<ButtonRelease-1>', self._on_main_sash_released, add='+')
        
        # Database selection (label + combo + admin buttons on one row).
        ttk.Label(self.left_panel, text="Database:").pack(pady=5)
        db_frame = ttk.Frame(self.left_panel)
        db_frame.pack(fill='x', padx=5)
        self.db_var = tk.StringVar()
        self.db_combo = ttk.Combobox(db_frame, textvariable=self.db_var)
        self.db_combo.pack(side='left', fill='x', expand=True)
        self.db_combo.bind('<<ComboboxSelected>>', self.on_db_selected)
        # Admin buttons live next to the combo so they're always near the
        # thing they act on; visibility is controlled by _refresh_admin_ui.
        self.add_db_btn = ttk.Button(
            db_frame, text="+", width=2, command=self.add_database
        )
        self.delete_db_btn = ttk.Button(
            db_frame, text="\u00d7", width=2, command=self.delete_database
        )
        self.add_db_btn.pack(side='left', padx=(4, 0))
        self.delete_db_btn.pack(side='left', padx=(2, 0))

        # Collection selection (label + combo + admin buttons on one row).
        coll_frame = ttk.Frame(self.left_panel)
        coll_frame.pack(fill='x', padx=5, pady=(4, 0))
        ttk.Label(coll_frame, text="Collection:").pack(side='left')
        self.collection_var = tk.StringVar()
        self.collection_combo = ttk.Combobox(coll_frame, textvariable=self.collection_var)
        self.collection_combo.pack(side='left', fill='x', expand=True, padx=5)
        self.collection_combo.bind('<<ComboboxSelected>>', self.on_collection_selected)
        self.add_coll_btn = ttk.Button(
            coll_frame, text="+", width=2, command=self.add_collection
        )
        self.delete_coll_btn = ttk.Button(
            coll_frame, text="\u00d7", width=2, command=self.delete_collection
        )
        self.add_coll_btn.pack(side='left', padx=(4, 0))
        self.delete_coll_btn.pack(side='left', padx=(2, 0))
        
        # Document list frame
        doc_frame = ttk.Frame(self.left_panel)
        doc_frame.pack(fill='both', expand=True, pady=5)
        
        # Document list header
        doc_header = ttk.Frame(doc_frame)
        doc_header.pack(fill='x')
        ttk.Label(doc_header, text="Compounds:").pack(side='left')
        ttk.Button(doc_header, text="Download CSV", command=self.download_table_csv).pack(side='right', padx=5)
        ttk.Button(doc_header, text="Manage Columns", command=self.manage_columns).pack(side='right', padx=5)
        ttk.Button(doc_header, text="Molecular Search", command=self.open_molecular_search).pack(side='right', padx=5)
        
        # Create Treeview with current columns
        self.create_document_table(doc_frame)
        
        # Document management buttons
        doc_btn_frame = ttk.Frame(self.left_panel)
        doc_btn_frame.pack(fill='x', padx=5, pady=5)
        ttk.Button(doc_btn_frame, text="Add Compound", command=self.add_document).pack(side='left', padx=2)
        ttk.Button(doc_btn_frame, text="Delete Compound", command=self.delete_document).pack(side='left', padx=2)
        
        # Add CSV import button to document management buttons
        ttk.Button(doc_btn_frame, text="Import CSV", command=self.import_csv).pack(side='left', padx=2)
        
        # Document details. A vertical split keeps the molecule preview and
        # editable properties visible even when the window is resized.
        self.detail_paned = ttk.PanedWindow(self.right_panel, orient='vertical')
        self.detail_paned.pack(fill='both', expand=True)

        self.molecule_panel = ttk.LabelFrame(self.detail_paned, text="Molecule", width=320, height=240)
        self.doc_display = ttk.LabelFrame(self.detail_paned, text="Properties", width=320, height=320)
        # Explicit propagate(False) keeps the panes from collapsing to zero
        # height when their child widgets are temporarily hidden during resize.
        self.molecule_panel.pack_propagate(False)
        self.doc_display.pack_propagate(False)
        self.detail_paned.add(self.molecule_panel, weight=1)
        self.detail_paned.add(self.doc_display, weight=3)

        self.mol_label = ttk.Label(
            self.molecule_panel,
            text="Select a compound to view its structure",
            anchor='center',
        )
        self.mol_label.pack(fill='both', expand=True, padx=8, pady=8)
        self._current_molecule_smiles = None
        self._mol_render_after_id = None
        self.molecule_panel.bind('<Configure>', self._on_molecule_panel_configure)
        
        # Initialize
        self.client = None  # Will be set after login

        # Place the main sash so the left (table) and right (details) panels
        # start with a sensible split independent of the natural sizes the
        # children would otherwise claim.
        self.after(50, self._set_initial_sashpos)

        # Show login dialog immediately
        self.after(100, self._show_initial_login)
        
        # Mark initialization as complete
        self.initializing = False

    def _set_initial_sashpos(self):
        """Place the horizontal main sash at the configured ratio."""
        self._apply_main_sash_ratio()

    def _apply_main_sash_ratio(self, *, total=None):
        """Move the main horizontal sash so it matches ``_main_sash_ratio``.

        Tk's PanedWindow doesn't support proportional sashes natively; if we
        don't reposition the sash on each resize the table will eat any extra
        width the user gives the window. We compute the target pixel position
        from the current container width and set the sash there, guarding
        against the feedback loop that would otherwise be triggered by
        ``ButtonRelease-1`` re-reading the value we just wrote.

        ``update_idletasks`` is intentionally avoided here because this method
        is called from inside a ``<Configure>`` handler, where forcing a sync
        relayout can re-enter the event loop and starve the resize.
        """
        try:
            if total is None:
                total = self.main_container.winfo_width()
                if total <= 1:
                    total = self.winfo_width() or 1200
            if total <= 1:
                return
            target = int(total * self._main_sash_ratio)
            target = max(120, min(total - 200, target))
            try:
                current = self.main_container.sashpos(0)
            except (tk.TclError, IndexError):
                current = -1
            # Tolerate single-pixel jitter from rounding so we don't fight a
            # stable layout.
            if abs(current - target) <= 1:
                return
            self._main_sash_applying = True
            try:
                self.main_container.sashpos(0, target)
            finally:
                # Clear the flag on the next idle tick so the ButtonRelease
                # that may follow our own configure-driven set doesn't get
                # interpreted as a user drag.
                self.after_idle(self._clear_main_sash_applying)
        except (tk.TclError, IndexError):
            self._main_sash_applying = False

    def _clear_main_sash_applying(self):
        self._main_sash_applying = False

    def _on_main_container_configure(self, event):
        """Re-apply the saved sash ratio whenever the container is resized."""
        if event.widget is not self.main_container:
            return
        # Only react to actual width changes; height-only Configure events
        # don't affect the sash position and can fire frequently when nested
        # widgets relayout.
        width = event.width if event.width else self.main_container.winfo_width()
        if width <= 1:
            return
        last_width = getattr(self, '_main_sash_last_width', None)
        if last_width == width:
            return
        self._main_sash_last_width = width
        self._apply_main_sash_ratio(total=width)

    def _on_main_sash_released(self, _event):
        """Capture the ratio whenever the user finishes dragging the sash."""
        if self._main_sash_applying:
            return
        try:
            total = self.main_container.winfo_width()
            if total <= 1:
                return
            current = self.main_container.sashpos(0)
            if current <= 0 or current >= total:
                return
            new_ratio = current / total
            # Clamp so a stray near-edge release doesn't permanently hide a panel.
            new_ratio = min(0.9, max(0.1, new_ratio))
            if abs(new_ratio - self._main_sash_ratio) < 0.005:
                return
            self._main_sash_ratio = new_ratio
            self._schedule_main_sash_save()
        except (tk.TclError, IndexError):
            pass

    def _schedule_main_sash_save(self):
        """Debounce persistence of the user's preferred sash ratio."""
        if self._main_sash_save_after_id is not None:
            try:
                self.after_cancel(self._main_sash_save_after_id)
            except tk.TclError:
                pass
        self._main_sash_save_after_id = self.after(500, self._save_main_sash_ratio)

    def _save_main_sash_ratio(self):
        self._main_sash_save_after_id = None
        try:
            self.config['main_sash_ratio'] = round(self._main_sash_ratio, 4)
            self._write_config()
        except Exception:
            logger.exception("Failed to persist main_sash_ratio")

    def _show_initial_login(self):
        """Show login dialog and initialize the chosen backend (remote or local)."""
        dialog = LoginDialog(self)
        if not dialog.result:
            self.destroy()  # Close the application if login is cancelled
            return

        result = dialog.result
        try:
            if result['mode'] == 'local':
                self.client = get_local_client(result['data_dir'])
                self.current_user = {
                    'username': 'local',
                    'auth_source': 'standalone',
                    'data_dir': result['data_dir'],
                    'login_time': datetime.now().isoformat(),
                }
                self.title(f"WetlabDB Browser  -  Standalone ({result['data_dir']})")
            else:
                self.client = get_mongo_client(
                    result['host'],
                    result['username'],
                    result['password'],
                    result['auth_source'],
                )
                self.current_user = {
                    'username': result['username'],
                    'auth_source': result['auth_source'],
                    'login_time': datetime.now().isoformat(),
                }
                self.title("MongoDB Browser")
            self._refresh_admin_ui()
            self.load_databases()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to connect: {str(e)}")
            self._show_initial_login()  # Retry login if connection fails

    # ------------------------------------------------------------------
    # Admin / write-access gating
    # ------------------------------------------------------------------
    def _admin_writes_allowed(self) -> bool:
        """Whether destructive admin actions (create/drop DB, create/drop collection) are allowed.

        Standalone mode owns its own files, so it always allows them.
        Remote mode requires the user to have ticked the "Admin access"
        checkbox in the login dialog.
        """
        mode = (self.config.get('mode') or '').lower()
        if mode == 'local':
            return True
        return bool(self.config.get('admin_access'))

    def _refresh_admin_ui(self) -> None:
        """Enable / disable the create+delete DB/collection buttons."""
        state = '!disabled' if self._admin_writes_allowed() else 'disabled'
        for btn in (
            getattr(self, 'add_db_btn', None),
            getattr(self, 'delete_db_btn', None),
            getattr(self, 'add_coll_btn', None),
            getattr(self, 'delete_coll_btn', None),
        ):
            if btn is not None:
                try:
                    btn.state([state])
                except tk.TclError:
                    pass

    def create_document_table(self, parent):
        table_frame = ttk.Frame(parent)
        table_frame.pack(fill='both', expand=True, padx=(10, 0))

        # Search bar in row 0, spanning both columns
        search_frame = ttk.Frame(table_frame)
        search_frame.grid(row=0, column=0, columnspan=2, sticky='ew', pady=5)

        ttk.Label(search_frame, text="Search:").pack(side='left', padx=5)
        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', self._on_search_change)
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side='left', fill='x', expand=True, padx=5)

        ttk.Label(search_frame, text="in column:").pack(side='left', padx=5)
        self.search_column = tk.StringVar(value="All")
        search_column_menu = ttk.OptionMenu(search_frame, self.search_column, "All",
                                            *self.visible_columns, command=self._on_search_change)
        search_column_menu.pack(side='left', padx=5)

        # Treeview and scrollbars. Use modest default column widths so the
        # table doesn't claim ~1200px of horizontal space and dominate the
        # main paned window. Columns stretch to fill the available area, and
        # the horizontal scrollbar handles overflow when the window is small.
        self.doc_list = ttk.Treeview(table_frame, columns=self.visible_columns, show='headings', height=10)
        for col in self.visible_columns:
            self.doc_list.heading(col, text=col, command=lambda c=col: self._sort_table(c))
            self.doc_list.column(col, width=120, minwidth=60, anchor='center', stretch=True)

        self.table_scrollbar = ttk.Scrollbar(table_frame, orient='vertical', command=self.doc_list.yview)
        self.doc_list.configure(yscrollcommand=self.table_scrollbar.set)

        self.table_xscrollbar = ttk.Scrollbar(table_frame, orient='horizontal', command=self.doc_list.xview)
        self.doc_list.configure(xscrollcommand=self.table_xscrollbar.set)

        self.doc_list.grid(row=1, column=0, sticky='nsew')
        self.table_scrollbar.grid(row=1, column=1, sticky='ns')
        self.table_xscrollbar.grid(row=2, column=0, sticky='ew')

        table_frame.grid_rowconfigure(1, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        self.doc_list.bind('<<TreeviewSelect>>', self.on_doc_selected)
        self.original_items = []
        self._sort_column = None
        self._sort_reverse = False

    def _sort_table(self, col):
        """Sort table contents when a column header is clicked"""
        # Get all items
        items = [(self.doc_list.set(item, col), item) for item in self.doc_list.get_children('')]
        
        # Sort items
        items.sort(key=lambda x: self._sort_key(x[0]), reverse=self._sort_reverse)
        
        # Rearrange items in sorted positions
        for index, (_, item) in enumerate(items):
            self.doc_list.move(item, '', index)
        
        # Update sort indicators
        if self._sort_column == col:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_reverse = False
            self._sort_column = col
        
        # Update column headers to show sort direction
        for column in self.visible_columns:
            if column == col:
                # Add arrow to indicate sort direction
                arrow = " ↓" if self._sort_reverse else " ↑"
                self.doc_list.heading(column, text=f"{column}{arrow}")
            else:
                # Remove arrow from other columns
                self.doc_list.heading(column, text=column)

    def _sort_key(self, value):
        """Convert value to appropriate type for sorting"""
        try:
            # Try to convert to float first
            return float(value)
        except ValueError:
            try:
                # Try to convert to int
                return int(value)
            except ValueError:
                # If all else fails, use string comparison
                return value.lower()

    def _on_search_change(self, *args):
        """Handle search/filter changes"""
        search_term = self.search_var.get().lower()
        search_column = self.search_column.get()
        
        # Clear the table
        self.doc_list.delete(*self.doc_list.get_children())
        
        # If no search term, show all items
        if not search_term:
            for item in self.original_items:
                self.doc_list.insert('', 'end', values=item)
            return
        
        # Filter items based on search term
        for item in self.original_items:
            if search_column == "All":
                # Search in all columns
                if any(search_term in str(value).lower() for value in item):
                    self.doc_list.insert('', 'end', values=item)
            else:
                # Search in specific column
                col_index = self.visible_columns.index(search_column)
                if search_term in str(item[col_index]).lower():
                    self.doc_list.insert('', 'end', values=item)

    def recreate_table(self):
        """Safely recreate the table with new columns"""
        # Get the parent frame
        parent = self.doc_list.master.master  # Go up two levels to get the document frame
        
        # Store current search and sort state
        current_search = self.search_var.get()
        current_search_column = self.search_column.get()
        current_sort_column = self._sort_column
        current_sort_reverse = self._sort_reverse
        
        # Unbind events and destroy old widgets
        self.doc_list.unbind('<<TreeviewSelect>>')
        self.doc_list.master.destroy()  # Destroy the table frame which includes both table and scrollbar
        
        # Create new table
        self.create_document_table(parent)
        
        # Restore search and sort state
        self.search_var.set(current_search)
        self.search_column.set(current_search_column)
        if current_sort_column:
            self._sort_table(current_sort_column)
            if current_sort_reverse:
                self._sort_table(current_sort_column)  # Click twice to reverse
        
        # Refresh the display
        self.refresh_display()

    def update_available_columns(self):
        """Update the set of all possible columns from the current collection"""
        try:
            if not self.db_var.get() or not self.collection_var.get():
                return
                
            db = self.client[self.db_var.get()]
            collection = db[self.collection_var.get()]
            
            # Get all unique fields from all documents
            all_fields = set()
            for doc in collection.find():
                self._extract_fields(doc, all_fields)
            
            # Update all_columns with new fields
            self.all_columns.update(all_fields)
            
            # Ensure default columns are always available
            self.all_columns.update(self.default_columns)
        except Exception as e:
            print(f"Error updating available columns: {e}")

    def _extract_fields(self, doc, fields, prefix=''):
        """Recursively extract all field names from a document"""
        for key, value in doc.items():
            if key != '_id':  # Skip MongoDB's _id field
                field_name = f"{prefix}{key}" if prefix else key
                fields.add(field_name)
                if isinstance(value, dict):
                    self._extract_fields(value, fields, f"{field_name}.")

    def manage_columns(self):
        # Update available columns from the database
        self.update_available_columns()
        
        # Create dialog window
        dialog = tk.Toplevel(self)
        dialog.title("Manage Columns")
        dialog.geometry("300x400")  # Reduced height to make it more manageable
        
        # Create main frame
        main_frame = ttk.Frame(dialog)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Create canvas and scrollbar
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
        column_vars = {}
        for col in sorted(self.all_columns):
            var = tk.BooleanVar(value=col in self.visible_columns)
            column_vars[col] = var
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
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill='x', padx=10, pady=10)
        ttk.Button(btn_frame, text="Apply", command=lambda: self._apply_column_changes(column_vars, dialog)).pack(side='right', padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side='right', padx=5)

    def _apply_column_changes(self, column_vars, dialog):
        # Update visible columns
        self.visible_columns = [col for col, var in column_vars.items() if var.get()]
        if not self.visible_columns:  # Ensure at least one column is visible
            self.visible_columns = ['ID']
            messagebox.showwarning("Warning", "At least one column must be visible. Keeping ID column.")
        
        # Recreate the table
        self.recreate_table()
        
        # Save configuration
        self.save_last_selection()
        
        dialog.destroy()

    # ------------------------------------------------------------------
    # Per-connection "last opened" memory
    # ------------------------------------------------------------------
    def _connection_key(self) -> str:
        """Return a stable identifier for the current backend connection.

        We key the saved "last database / collection" by this string so that
        switching between MongoDB and standalone (or between two MongoDB
        servers / two local folders) doesn't try to reopen a database that
        only exists on a *different* connection. That was the symptom of
        "after switching modes the saved DB silently falls back to the first
        alphabetical one".
        """
        mode = (self.config.get('mode') or 'remote').lower()
        if mode == 'local':
            data_dir = self.config.get('local_data_dir') or ''
            try:
                norm = os.path.normcase(os.path.normpath(data_dir))
            except Exception:
                norm = data_dir
            return f"local:{norm}"
        host = self.config.get('host_ip') or 'localhost'
        port = self.config.get('port') or 27017
        return f"remote:{host}:{port}"

    def _last_selection(self) -> dict[str, object]:
        """Return the saved selection dict for the current connection.

        Falls back to the legacy top-level ``last_database`` / ``last_collection``
        / ``visible_columns`` fields the very first time we see a connection
        (one-shot lazy migration), so users upgrading from a previous version
        don't lose their auto-restore on the connection they were last using.
        """
        key = self._connection_key()
        by_key = self.config.setdefault('last_selection_by_key', {})
        bucket = by_key.get(key)
        if isinstance(bucket, dict) and bucket:
            return bucket

        legacy_db = self.config.get('last_database')
        legacy_coll = self.config.get('last_collection')
        legacy_cols = self.config.get('visible_columns')
        if legacy_db or legacy_coll or legacy_cols:
            bucket = {}
            if legacy_db:
                bucket['last_database'] = legacy_db
            if legacy_coll:
                bucket['last_collection'] = legacy_coll
            if legacy_cols:
                bucket['visible_columns'] = list(legacy_cols)
            by_key[key] = bucket
            return bucket
        return {}

    def save_last_selection(self):
        """Persist current DB + collection + visible columns for this connection."""
        try:
            if self.initializing:
                return

            current_db = self.db_combo.get() or self.db_var.get()
            current_collection = self.collection_combo.get() or self.collection_var.get()

            if not current_db:
                return

            key = self._connection_key()
            by_key = self.config.setdefault('last_selection_by_key', {})
            bucket = by_key.setdefault(key, {})
            bucket['last_database'] = current_db
            bucket['visible_columns'] = list(self.visible_columns)
            if current_collection:
                bucket['last_collection'] = current_collection

            # Mirror to the legacy top-level fields too so anything still
            # reading them (older code paths, manual inspection of the JSON)
            # sees a sensible "most recent" value across all connections.
            self.config['last_database'] = current_db
            self.config['visible_columns'] = list(self.visible_columns)
            if current_collection:
                self.config['last_collection'] = current_collection

            self._write_config()
        except Exception:
            logger.exception("Failed to save last selection")

    def load_databases(self):
        """Populate the database dropdown and auto-restore the last selection."""
        try:
            databases = self.client.list_database_names()
        except Exception:
            logger.exception("list_database_names() failed")
            return

        if not databases:
            logger.info("No databases visible to this user")
            return

        self.db_combo['values'] = databases

        saved = self._last_selection()
        last_db = saved.get('last_database')
        saved_columns = saved.get('visible_columns')
        logger.info(
            "Restoring selection for connection %r: db=%r, collection=%r",
            self._connection_key(), last_db, saved.get('last_collection'),
        )

        if last_db and last_db in databases:
            target_db = last_db
        else:
            if last_db:
                logger.info(
                    "Saved database %r not found on this connection (available: %s);"
                    " falling back to %r",
                    last_db, databases, databases[0],
                )
            target_db = databases[0]

        self.db_var.set(target_db)
        self.db_combo.set(target_db)

        if saved_columns:
            self.visible_columns = list(saved_columns)
            self.recreate_table()

        self.on_db_selected(None)

    def on_db_selected(self, event):
        try:
            current_db = self.db_combo.get() or self.db_var.get()
            if not current_db:
                return

            self.db_var.set(current_db)

            db = self.client[current_db]
            try:
                collections = db.list_collection_names()
            except Exception:
                logger.exception("list_collection_names() failed for db=%r", current_db)
                self.collection_combo['values'] = []
                self.collection_var.set('')
                return

            if not collections:
                self.collection_combo['values'] = []
                self.collection_var.set('')
                return

            self.collection_combo['values'] = collections

            saved = self._last_selection()
            saved_db = saved.get('last_database')
            last_collection = saved.get('last_collection')
            # Only honour the saved collection if we're on the database it was
            # saved against -- otherwise it's almost certainly a name from a
            # different DB that just happens to exist here too.
            if (
                saved_db == current_db
                and last_collection
                and last_collection in collections
            ):
                target_collection = last_collection
            else:
                target_collection = collections[0]

            self.collection_var.set(target_collection)
            self.collection_combo.set(target_collection)
            self.on_collection_selected(None)
            if not self.initializing:
                self.save_last_selection()
        except Exception:
            logger.exception("on_db_selected failed")

    def on_doc_selected(self, event):
        try:
            # Clear previous display
            for widget in self.doc_display.winfo_children():
                widget.destroy()
            self._clear_molecule_display()
            
            # Get selected document
            selection = self.doc_list.selection()
            if not selection:
                print("No selection found")
                return
                
            # Get the document from MongoDB
            db = self.client[self.db_var.get()]
            collection = db[self.collection_var.get()]
            
            # Get the _id from the last column of the selected item
            doc_id = self.doc_list.item(selection[0])['values'][-1]
            
            # Get the document using _id
            doc = collection.find_one({'_id': _coerce_id(doc_id)})
            
            if doc:
                # Store _id for later use
                doc_id = doc['_id']
                # Remove _id from the document before creating the form
                del doc['_id']
                
                # Process file fields to ensure they're handled correctly
                for key, value in doc.items():
                    if key in compound_form and compound_form[key]['type'] == 'file':
                        if isinstance(value, dict) and 'filename' in value and 'data' in value:
                            # Keep the file data as is
                            pass
                        else:
                            # If it's not in the correct format, set it to None
                            doc[key] = None
                    elif key == 'SMILES' and value:
                        canon = canonicalize_smiles(value)
                        if canon is not None:
                            doc[key] = canon
                
                # Create main container
                main_container = ttk.Frame(self.doc_display)
                main_container.pack(fill='both', expand=True, padx=5, pady=5)
                
                # Create button container first to ensure it's always visible
                button_container = ttk.Frame(main_container)
                button_container.pack(side='bottom', fill='x', pady=5)
                
                # Create a frame for the canvas and scrollbar
                canvas_frame = ttk.Frame(main_container)
                canvas_frame.pack(side='top', fill='both', expand=True, pady=(0, 5))
                
                # Scrollbar is always packed first on the right so the canvas
                # below claims the remaining width via fill='both', expand=True.
                # Earlier versions auto-hid the scrollbar and manually resized
                # the canvas with ``canvas.configure(width=...)``; that ran on
                # every form ``<Configure>``, sometimes received a stale 1px
                # parent width, and made the entire properties panel briefly
                # disappear during a window resize.
                scrollbar = ttk.Scrollbar(canvas_frame, orient='vertical')
                scrollbar.pack(side='right', fill='y')

                canvas = tk.Canvas(canvas_frame, bg="#f5f5f5", highlightthickness=0)
                canvas.pack(side='left', fill='both', expand=True)

                canvas.configure(yscrollcommand=scrollbar.set)
                scrollbar.configure(command=canvas.yview)

                # Create a frame inside the canvas to hold the form.
                form_container = ttk.Frame(canvas)
                form = JSONForm(form_container, doc, config=self.config)
                form.pack(fill='both', expand=True, pady=5)
                canvas_window = canvas.create_window((0, 0), window=form_container, anchor='nw', tags='form')

                def _update_scrollregion(event=None):
                    try:
                        if canvas.winfo_exists():
                            canvas.configure(scrollregion=canvas.bbox('all'))
                    except tk.TclError:
                        pass

                def _match_form_to_canvas(event):
                    try:
                        if canvas.winfo_exists() and event.width > 1:
                            canvas.itemconfig(canvas_window, width=event.width)
                    except tk.TclError:
                        pass

                form_container.bind('<Configure>', _update_scrollregion)
                canvas.bind('<Configure>', _match_form_to_canvas)
                
                # Bind mouse wheel to the canvas for scrolling
                def _on_mousewheel(event):
                    if event.num == 4 or event.delta > 0:
                        canvas.yview_scroll(-1, "units")
                    elif event.num == 5 or event.delta < 0:
                        canvas.yview_scroll(1, "units")

                def _on_mousewheel_win(event):
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                
                # Bind different events based on platform
                if self.winfo_toplevel().tk.call('tk', 'windowingsystem') == 'win32':
                    canvas.bind_all("<MouseWheel>", _on_mousewheel_win)
                else:
                    canvas.bind_all("<Button-4>", _on_mousewheel)
                    canvas.bind_all("<Button-5>", _on_mousewheel)
                
                # Function to unbind mouse wheel when the form is destroyed
                def _unbind_mousewheel():
                    if self.winfo_toplevel().tk.call('tk', 'windowingsystem') == 'win32':
                        canvas.unbind_all("<MouseWheel>")
                    else:
                        canvas.unbind_all("<Button-4>")
                        canvas.unbind_all("<Button-5>")
                
                # Add submit button
                def submit():
                    try:
                        # Get the form data
                        data = form.to_json()
                        
                        # Update the document
                        collection.update_one(
                            {"_id": doc_id},
                            {"$set": data}
                        )
                        
                        # Unbind mousewheel
                        _unbind_mousewheel()
                        
                        # Clear the form container
                        for widget in self.doc_display.winfo_children():
                            widget.destroy()
                        
                        # Refresh display
                        self.refresh_display()
                        
                    except Exception as e:
                        print(f"Error updating document: {e}")
                        _unbind_mousewheel()
                        for widget in self.doc_display.winfo_children():
                            widget.destroy()
                
                update_btn = ttk.Button(button_container, text="Update", command=submit)
                update_btn.pack(side='left', padx=5)

                # Refresh the scroll region once the canvas has its real size.
                self.after(50, _update_scrollregion)

                # Display molecule if SMILES is present
                if 'SMILES' in doc and doc['SMILES']:
                    self.display_molecule(doc['SMILES'])
            else:
                print("No document found with _id")
                messagebox.showwarning("Warning", "Could not find the selected document in the database.")
        except Exception as e:
            print(f"Error in document selection: {e}")
            messagebox.showerror("Error", f"Error loading document: {str(e)}")

    def _on_molecule_panel_configure(self, event):
        """Re-render the molecule preview after resize settles."""
        if event.widget == self.molecule_panel:
            self._schedule_molecule_render()

    def _schedule_molecule_render(self):
        if self._mol_render_after_id:
            self.after_cancel(self._mol_render_after_id)
        self._mol_render_after_id = self.after(100, self._render_molecule_preview)

    def _clear_molecule_display(self):
        self._current_molecule_smiles = None
        if self._mol_render_after_id:
            self.after_cancel(self._mol_render_after_id)
            self._mol_render_after_id = None
        self.mol_label.configure(
            image="",
            text="Select a compound to view its structure",
        )
        self.mol_label.image = None

    def display_molecule(self, smiles):
        self._current_molecule_smiles = smiles.strip() if smiles else None
        self._schedule_molecule_render()

    def _render_molecule_preview(self):
        self._mol_render_after_id = None
        smiles = self._current_molecule_smiles
        if not smiles:
            self._clear_molecule_display()
            return

        try:
            width = max(80, self.molecule_panel.winfo_width() - 24)
            height = max(80, self.molecule_panel.winfo_height() - 44)
            size = max(80, min(width, height, 400))

            png = render_to_png_bytes(smiles, width=size, height=size)
            if png is None:
                logger.debug("display_molecule could not render %r", smiles)
                self.mol_label.configure(image="", text="Could not render structure")
                self.mol_label.image = None
                return

            img = Image.open(io.BytesIO(png))
            photo = ImageTk.PhotoImage(img)
            self.mol_label.configure(image=photo, text="")
            self.mol_label.image = photo  # keep reference
        except Exception:
            logger.exception("Error displaying molecule %r", smiles)
            self.mol_label.configure(image="", text="Could not render structure")
            self.mol_label.image = None

    def add_document(self):
        def submit(data):
            db = self.client[self.db_var.get()]
            collection = db[self.collection_var.get()]
            result = collection.insert_one(data)
            self.refresh_display()
        
        self._open_form("Add Document", None, submit)

    def delete_document(self):
        selection = self.doc_list.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a document to delete")
            return
            
        if messagebox.askyesno("Confirm", "Are you sure you want to delete this document?"):
            try:
                # Get the _id from the last column of the selected item
                doc_id_str = self.doc_list.item(selection[0])['values'][-1]
                
                # Convert string _id to ObjectId (or string in standalone mode)
                doc_id = _coerce_id(doc_id_str)
                
                # Get MongoDB client and collection
                db = self.client[self.db_var.get()]
                collection = db[self.collection_var.get()]
                
                # Delete using the correct _id
                result = collection.delete_one({'_id': doc_id})
                
                if result.deleted_count == 0:
                    messagebox.showwarning("Warning", "Document not found in database")
                else:
                    print(f"Deleted document with _id: {doc_id}")
                
                # Refresh the display
                self.refresh_display()
            except Exception as e:
                print(f"Error deleting document: {e}")
                messagebox.showerror("Error", f"Error deleting document: {str(e)}")

    def on_collection_selected(self, event):
        try:
            # Get the current collection value
            current_collection = self.collection_combo.get()  # Get from combo first
            if not current_collection:
                current_collection = self.collection_var.get()  # Fall back to var if needed
                
            
            if not current_collection:
                print("No collection selected")
                return
                
            # Update the var to match the combo
            self.collection_var.set(current_collection)
            
            self.refresh_display()
            if not self.initializing:
                self.save_last_selection()
        except Exception as e:
            print(f"Error selecting collection: {e}")

    def refresh_display(self):
        try:
            # Update available columns
            self.update_available_columns()
            
            # Store the current selection
            selected_items = self.doc_list.selection()
            selected_ids = [self.doc_list.item(item)['values'][-1] for item in selected_items]  # Get _id from values
            
            # Clear the document display first to prevent widget access issues
            for widget in self.doc_display.winfo_children():
                widget.destroy()
            
            # Clear and reload the list
            self.doc_list.delete(*self.doc_list.get_children())
            
            # Get the current collection
            db = self.client[self.db_var.get()]
            collection = db[self.collection_var.get()]
            
            # Reload documents
            self.original_items = []  # Clear original items
            cursor = collection.find()
            docs = list(cursor)  # Convert cursor to list
            
            for doc in docs:
                values = []
                for col in self.visible_columns:
                    # Handle nested fields (e.g., "parent.child")
                    value = doc
                    for key in col.split('.'):
                        if isinstance(value, dict):
                            value = value.get(key, '')
                        else:
                            value = ''
                            break
                    values.append(str(value) if value is not None else '')
                
                # Add _id as the last value
                values.append(str(doc['_id']))
                
                # Store the values for filtering
                self.original_items.append(values)
                
                # Only insert if it matches the current search
                search_term = self.search_var.get().lower()
                if not search_term or any(search_term in str(value).lower() for value in values[:-1]):  # Exclude _id from search
                    item = self.doc_list.insert('', 'end', values=values)
                    
                    # Restore selection if this item was selected
                    if str(doc['_id']) in selected_ids:
                        self.doc_list.selection_add(item)
                        # Use after() to delay the selection event until after the refresh is complete
                        self.after(100, lambda: self.on_doc_selected(None))
            
            # Clear molecule display
            self._clear_molecule_display()
            
        except Exception as e:
            print(f"Error during refresh: {e}")
            messagebox.showerror("Error", f"Error refreshing display: {str(e)}")

    # ------------------------------------------------------------------
    # Database / collection admin actions
    # ------------------------------------------------------------------
    def _require_admin(self) -> bool:
        """Show a friendly error and return False when admin actions are disabled.

        The buttons are already greyed out when this returns False, but a
        defensive check here makes it impossible for accidental keyboard
        bindings (or future code paths) to bypass the gate.
        """
        if self._admin_writes_allowed():
            return True
        messagebox.showinfo(
            "Admin access required",
            "Creating or deleting databases and collections is disabled.\n\n"
            "Log out and re-login with the \"Admin access\" checkbox ticked, "
            "or switch to standalone mode.",
        )
        return False

    def add_database(self):
        """Create a new database on the current connection.

        Both backends create databases lazily (when the first collection in
        them is created), so we ask for both names at once.
        """
        if not self._require_admin():
            return
        name = simpledialog.askstring("New Database", "Enter database name:")
        if not name:
            return
        name = name.strip()
        if not name:
            return
        try:
            existing = self.client.list_database_names()
        except Exception as exc:
            messagebox.showerror("Error", f"Could not list databases:\n{exc}")
            return
        if name in existing:
            messagebox.showerror("Error", f"Database '{name}' already exists")
            return

        coll_name = simpledialog.askstring(
            "Initial Collection",
            f"Database '{name}' will be created when its first collection exists.\n"
            "Enter the name of the initial collection:",
            initialvalue="Compounds",
        )
        if not coll_name:
            return
        coll_name = coll_name.strip()
        if not coll_name:
            return

        try:
            self.client[name].create_collection(coll_name)
        except Exception as exc:
            messagebox.showerror("Error", f"Could not create database:\n{exc}")
            return

        # Re-read database list, jump to the new one, and persist.
        try:
            databases = self.client.list_database_names()
            self.db_combo['values'] = databases
        except Exception:
            logger.exception("Could not refresh database list after create")
        self.db_var.set(name)
        self.db_combo.set(name)
        self.on_db_selected(None)
        self.save_last_selection()

    def delete_database(self):
        """Drop the currently-selected database after a typed-name confirmation."""
        if not self._require_admin():
            return
        current_db = self.db_combo.get() or self.db_var.get()
        if not current_db:
            messagebox.showwarning("Warning", "Please select a database to delete")
            return

        typed = simpledialog.askstring(
            "Confirm delete database",
            f"This will permanently delete the database '{current_db}' and ALL of its collections.\n\n"
            f"Type the database name to confirm:",
        )
        if typed is None:
            return
        if typed.strip() != current_db:
            messagebox.showinfo("Cancelled", "Database name did not match. Nothing was deleted.")
            return

        try:
            self.client.drop_database(current_db)
        except Exception as exc:
            messagebox.showerror("Error", f"Could not delete database:\n{exc}")
            return

        # Forget the per-connection memory for this DB so we don't try to
        # auto-reopen a database that no longer exists next session.
        by_key = self.config.setdefault('last_selection_by_key', {})
        bucket = by_key.get(self._connection_key())
        if isinstance(bucket, dict) and bucket.get('last_database') == current_db:
            bucket.pop('last_database', None)
            bucket.pop('last_collection', None)

        # Reset the UI and reload from scratch.
        self.db_var.set('')
        self.db_combo.set('')
        self.collection_var.set('')
        self.collection_combo.set('')
        self.collection_combo['values'] = []
        self.load_databases()

    def add_collection(self):
        if not self._require_admin():
            return
        current_db = self.db_combo.get() or self.db_var.get()
        if not current_db:
            messagebox.showwarning("Warning", "Please select a database first")
            return
        name = simpledialog.askstring("New Collection", "Enter collection name:")
        if not name:
            return
        name = name.strip()
        if not name:
            return
        try:
            self.client[current_db].create_collection(name)
        except Exception as exc:
            messagebox.showerror("Error", f"Could not create collection:\n{exc}")
            return
        self.on_db_selected(None)
        self.collection_combo.set(name)
        self.on_collection_selected(None)
        self.save_last_selection()

    def delete_collection(self):
        if not self._require_admin():
            return
        current_db = self.db_combo.get() or self.db_var.get()
        current_collection = self.collection_combo.get() or self.collection_var.get()
        if not current_db or not current_collection:
            messagebox.showwarning("Warning", "Please select a collection to delete")
            return

        if not messagebox.askyesno(
            "Confirm",
            f"Delete collection '{current_collection}' from database '{current_db}'?\n"
            "This permanently removes all documents in it.",
        ):
            return

        try:
            self.client[current_db].drop_collection(current_collection)
        except Exception as exc:
            messagebox.showerror("Error", f"Could not delete collection:\n{exc}")
            return

        # Drop the per-connection memory of this collection.
        by_key = self.config.setdefault('last_selection_by_key', {})
        bucket = by_key.get(self._connection_key())
        if isinstance(bucket, dict) and bucket.get('last_collection') == current_collection:
            bucket.pop('last_collection', None)

        self.on_db_selected(None)
    def _open_form(self, title, initial, on_submit):
        win = tk.Toplevel(self)
        win.title(title.replace("Document", "Compound"))  # Replace Document with Compound in title
        win.geometry("800x860")

        # Create main container
        main_container = ttk.Frame(win)
        main_container.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Create button container first to ensure it's always visible
        button_container = ttk.Frame(main_container)
        button_container.pack(side='bottom', fill='x', pady=5)
        
        # Create a frame for the canvas and scrollbar
        canvas_frame = ttk.Frame(main_container)
        canvas_frame.pack(side='top', fill='both', expand=True, pady=(0, 5))
        
        # Create canvas and scrollbar for the form
        canvas = tk.Canvas(canvas_frame, bg="#f5f5f5", highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient='vertical', command=canvas.yview)
        
        # Configure canvas
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Pack canvas first - we'll manage the scrollbar visibility later
        canvas.pack(side='left', fill='both', expand=True)
        
        # Create a frame inside the canvas to hold the form
        form_container = ttk.Frame(canvas, padding=(10, 5))

        # Pass is_new_document=True when adding a new document
        is_new_document = title == "Add Document"
        
        # Process initial data properly
        if is_new_document:
            # Create a proper dictionary with field info, not just the form schema
            processed_initial = {}
            for key, field_info in compound_form.items():
                field_type = field_info['type']
                default_value = field_info['default']
                
                # Convert default value to proper type
                if field_type == 'boolean':
                    processed_initial[key] = bool(default_value)
                elif field_type == 'float':
                    processed_initial[key] = float(default_value)
                elif field_type == 'file':
                    processed_initial[key] = None
                else:  # string or dict
                    processed_initial[key] = default_value
            
            form = JSONForm(form_container, processed_initial, is_new_document=is_new_document, config=self.config)
        else:
            form = JSONForm(form_container, initial, is_new_document=is_new_document, config=self.config)
            
        form.pack(fill='both', expand=True, pady=5)
        
        # Add the form container to the canvas
        canvas_window = canvas.create_window((0, 0), window=form_container, anchor='nw', tags='form')
        
        # Configure the canvas scroll region when the form size changes
        def configure_scroll_region(event=None):
            # Update the scroll region to encompass the form
            canvas.configure(scrollregion=canvas.bbox('all'))
            # Update the canvas window width to match the canvas width
            canvas.itemconfig(canvas_window, width=canvas.winfo_width())
            
            # Check if scrollbar is needed
            check_scrollbar_needed()
        
        # Function to check if scrollbar is needed and show/hide it accordingly
        def check_scrollbar_needed():
            try:
                if not form_container.winfo_exists() or not canvas.winfo_exists():
                    return
                
                form_height = form_container.winfo_reqheight()
                canvas_height = canvas.winfo_height()
                
                # Only show scrollbar if form is taller than canvas
                if form_height > canvas_height:
                    if not scrollbar.winfo_ismapped():
                        scrollbar.pack(side='right', fill='y')
                        # Adjust canvas width to account for scrollbar
                        canvas.configure(width=canvas_frame.winfo_width() - scrollbar.winfo_reqwidth())
                    else:
                        scrollbar.pack_forget()
                        # Restore canvas width
                        canvas.configure(width=canvas_frame.winfo_width())
            except (tk.TclError, RuntimeError):
                # Widget doesn't exist anymore or was destroyed
                pass
        
        # Bind the configure event to the form container
        form_container.bind('<Configure>', configure_scroll_region)
        
        # Force an initial update of the scroll region
        def force_update():
            try:
                if form_container.winfo_exists() and canvas.winfo_exists():
                    # This forces the canvas to recalculate its scroll region
                    form_container.update_idletasks()
                    canvas.configure(scrollregion=canvas.bbox('all'))
                    # Set the canvas window width to match the canvas width
                    canvas.itemconfig(canvas_window, width=canvas.winfo_width())
                    # Check if scrollbar is needed
                    check_scrollbar_needed()
            except (tk.TclError, RuntimeError):
                # Widget doesn't exist anymore or was destroyed
                pass
        
        # Schedule the update after everything is created and displayed
        win.after(100, force_update)
        
        # Bind mouse wheel to the canvas for scrolling - handle cross-platform differences
        def _on_mousewheel(event):
            # Only scroll if scrollbar is visible
            if scrollbar.winfo_ismapped():
                if event.num == 4 or event.delta > 0:
                    canvas.yview_scroll(-1, "units")
                elif event.num == 5 or event.delta < 0:
                    canvas.yview_scroll(1, "units")
        
        def _on_mousewheel_win(event):
            # Only scroll if scrollbar is visible
            if scrollbar.winfo_ismapped():
                canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        # Bind different events based on platform
        if win.tk.call('tk', 'windowingsystem') == 'win32':
            canvas.bind_all("<MouseWheel>", _on_mousewheel_win)
        else:
            canvas.bind_all("<Button-4>", _on_mousewheel)
            canvas.bind_all("<Button-5>", _on_mousewheel)
        
        # Add keyboard navigation (Page Up/Down)
        def _on_page_up(event):
            # Only scroll if scrollbar is visible
            if scrollbar.winfo_ismapped():
                canvas.yview_scroll(-1, "pages")
                return "break"  # Prevent default behavior
        
        def _on_page_down(event):
            # Only scroll if scrollbar is visible
            if scrollbar.winfo_ismapped():
                canvas.yview_scroll(1, "pages")
                return "break"  # Prevent default behavior
        
        canvas.bind_all("<Prior>", _on_page_up)  # Page Up
        canvas.bind_all("<Next>", _on_page_down)  # Page Down
        
        # Add arrow key navigation
        def _on_up_arrow(event):
            # Only scroll if scrollbar is visible
            if scrollbar.winfo_ismapped():
                canvas.yview_scroll(-3, "units")
                return "break"
        
        def _on_down_arrow(event):
            # Only scroll if scrollbar is visible
            if scrollbar.winfo_ismapped():
                canvas.yview_scroll(3, "units")
                return "break"
        
        canvas.bind_all("<Control-Up>", _on_up_arrow)
        canvas.bind_all("<Control-Down>", _on_down_arrow)
        
        # Function to unbind all navigation events
        def _unbind_navigation():
            if win.tk.call('tk', 'windowingsystem') == 'win32':
                canvas.unbind_all("<MouseWheel>")
            else:
                canvas.unbind_all("<Button-4>")
                canvas.unbind_all("<Button-5>")
            canvas.unbind_all("<Prior>")
            canvas.unbind_all("<Next>")
            canvas.unbind_all("<Control-Up>")
            canvas.unbind_all("<Control-Down>")

        # Create button container
        button_container = ttk.Frame(main_container)
        button_container.pack(fill='x', pady=5)

        def submit():
            try:
                data = form.to_json()
                on_submit(data)
                _unbind_navigation()  # Unbind navigation events before destroying the window
                win.destroy()
                self.refresh_display()
            except Exception as e:
                print(f"Error in form submission: {e}")
                messagebox.showerror("Error", str(e))

        submit_btn = ttk.Button(button_container, text="Submit", command=submit)
        submit_btn.pack(side='right', padx=5)
        
        # Bind window resize event to recalculate form layout
        def _on_window_resize(event):
            try:
                if win.winfo_exists() and canvas.winfo_exists() and form_container.winfo_exists():
                    # Delay the update to avoid multiple rapid recalculations
                    win.after(100, force_update)
            except (tk.TclError, RuntimeError):
                # Widget doesn't exist anymore or was destroyed
                pass
        
        win.bind("<Configure>", _on_window_resize)
        
        # Bind window close event to unbind navigation events
        win.protocol("WM_DELETE_WINDOW", lambda: [_unbind_navigation(), win.destroy()])

    def open_molecular_search(self):
        if not self.collection_var.get():
            messagebox.showwarning("Warning", "Please select a collection first")
            return
        
        db = self.client[self.db_var.get()]
        collection = db[self.collection_var.get()]
        MolecularSearchWindow(self, collection)

    def _write_config(self):
        """Persist :attr:`self.config` to disk via :class:`AppConfig`."""
        try:
            if self.initializing:
                return
            self.app_config = AppConfig.from_dict(self.config)
            self.app_config.save()
        except Exception as e:
            print(f"Error writing config: {e}")

    def import_csv(self):
        """Import data from a CSV file"""
        from wetlabdb.services import import_csv as _import_csv

        if not self.collection_var.get():
            messagebox.showwarning("Warning", "Please select a collection first")
            return

        file_path = filedialog.askopenfilename(
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not file_path:
            return

        try:
            df = pd.read_csv(file_path)

            dialog = ColumnSelectionDialog(self, df.columns.tolist())
            self.wait_window(dialog)
            if not dialog.result:
                return
            identifier_col, data_cols = dialog.result

            db = self.client[self.db_var.get()]
            collection = db[self.collection_var.get()]

            summary = _import_csv(collection, df, identifier_col, data_cols)

            messagebox.showinfo(
                "Import Complete",
                f"Import completed successfully:\n"
                f"Updated: {summary.updated} documents\n"
                f"Created: {summary.created} documents",
            )
            self.refresh_display()

        except Exception as e:
            messagebox.showerror("Error", f"Error importing CSV: {str(e)}")

    def download_table_csv(self):
        """Download the current table contents as a CSV file"""
        from wetlabdb.services import export_csv as _export_csv

        if not self.doc_list.get_children():
            messagebox.showwarning("Warning", "No data to export")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="compounds_export.csv",
        )
        if not file_path:
            return

        try:
            headers = self.visible_columns
            rows = [
                self.doc_list.item(item)["values"][:-1]
                for item in self.doc_list.get_children()
            ]
            _export_csv(file_path, rows, headers)
            messagebox.showinfo("Success", f"Data exported successfully to {file_path}")

        except Exception as e:
            messagebox.showerror("Error", f"Error exporting data: {str(e)}")

    def _on_window_configure(self, event):
        """Handle window configure events with debouncing"""
        # Only handle if it's the main window being resized
        if event.widget == self:
            current_width = self.winfo_width()
            current_height = self.winfo_height()
            
            # Check if size actually changed
            if current_width != self.last_width or current_height != self.last_height:
                self.last_width = current_width
                self.last_height = current_height
                
                # Cancel any pending update
                if self.resize_after_id:
                    self.after_cancel(self.resize_after_id)
                
                # Schedule a new update
                self.resize_after_id = self.after(100, self._update_layout)
    
    def _update_layout(self):
        """Update layout after resize has settled"""
        try:
            # The selected-compound form already responds to Configure events
            # and maintains its own scroll region. Rebuilding it here on every
            # resize caused the properties panel to flicker or disappear.
            self._schedule_molecule_render()
            self.update_idletasks()
        finally:
            self.resize_after_id = None


# Public name going forward; the original ``MongoBrowser`` is kept as an alias
# for any external code (or scripts) that still import it by the old name.
WetlabDBApp = MongoBrowser


def main() -> None:
    """Launch the WetlabDB desktop application."""
    app = WetlabDBApp()
    app.mainloop()
