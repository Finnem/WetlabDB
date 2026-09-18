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
class LoginDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("WetlabDB Login")
        self.geometry("460x340")
        self.parent = parent

        # Make dialog modal
        self.transient(parent)
        self.grab_set()

        # Center the dialog
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

        # Create main frame
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill='both', expand=True)

        # ---- Mode selector ------------------------------------------------
        # Default to whatever is in the config; if pymongo is missing we can
        # only offer standalone mode.
        default_mode = parent.config.get('mode', 'remote')
        if not PYMONGO_AVAILABLE:
            default_mode = 'local'
        self.mode_var = tk.StringVar(value=default_mode)

        mode_frame = ttk.LabelFrame(main_frame, text="Connection mode", padding=5)
        mode_frame.pack(fill='x', pady=(0, 8))

        remote_radio = ttk.Radiobutton(
            mode_frame, text="MongoDB server (remote)",
            variable=self.mode_var, value='remote',
            command=self._on_mode_change,
        )
        remote_radio.pack(side='left', padx=5)
        if not PYMONGO_AVAILABLE:
            remote_radio.state(['disabled'])

        ttk.Radiobutton(
            mode_frame, text="Standalone (local file)",
            variable=self.mode_var, value='local',
            command=self._on_mode_change,
        ).pack(side='left', padx=5)

        # ---- Remote (MongoDB) section ------------------------------------
        self.remote_frame = ttk.Frame(main_frame)

        ttk.Label(self.remote_frame, text="Host IP:").grid(row=0, column=0, sticky='w', pady=2)
        self.host_ip_var = tk.StringVar(value=parent.config.get('host_ip', "localhost"))
        ttk.Entry(self.remote_frame, textvariable=self.host_ip_var, width=30).grid(row=0, column=1, sticky='ew', pady=2)

        ttk.Label(self.remote_frame, text="Port:").grid(row=1, column=0, sticky='w', pady=2)
        self.port_var = tk.StringVar(value=parent.config.get('port', "27017"))
        ttk.Entry(self.remote_frame, textvariable=self.port_var, width=30).grid(row=1, column=1, sticky='ew', pady=2)

        ttk.Label(self.remote_frame, text="Username:").grid(row=2, column=0, sticky='w', pady=2)
        self.username_var = tk.StringVar(value=parent.config.get('username', None))
        ttk.Entry(self.remote_frame, textvariable=self.username_var, width=30).grid(row=2, column=1, sticky='ew', pady=2)

        ttk.Label(self.remote_frame, text="Password:").grid(row=3, column=0, sticky='w', pady=2)
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(self.remote_frame, textvariable=self.password_var, show="*", width=30)
        self.password_entry.grid(row=3, column=1, sticky='ew', pady=2)

        ttk.Label(self.remote_frame, text="Auth Source:").grid(row=4, column=0, sticky='w', pady=2)
        self.auth_source_var = tk.StringVar(value=parent.config.get('auth_source', "admin"))
        ttk.Entry(self.remote_frame, textvariable=self.auth_source_var, width=30).grid(row=4, column=1, sticky='ew', pady=2)

        # Admin-access opt-in. Off by default so a routine login can't
        # accidentally enable destructive UI actions on a live server.
        self.admin_access_var = tk.BooleanVar(
            value=bool(parent.config.get('admin_access', False))
        )
        ttk.Checkbutton(
            self.remote_frame,
            text="Admin access (allow create/delete database & collection)",
            variable=self.admin_access_var,
        ).grid(row=5, column=0, columnspan=2, sticky='w', pady=(6, 2))

        self.remote_frame.columnconfigure(1, weight=1)

        # ---- Standalone (local) section ----------------------------------
        self.local_frame = ttk.Frame(main_frame)

        ttk.Label(
            self.local_frame,
            text=("Standalone mode stores data in JSON files on disk.\n"
                  "No MongoDB server is required."),
            justify='left',
        ).grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, 6))

        ttk.Label(self.local_frame, text="Data folder:").grid(row=1, column=0, sticky='w', pady=2)
        self.local_dir_var = tk.StringVar(
            value=parent.config.get('local_data_dir', _default_local_data_dir())
        )
        ttk.Entry(
            self.local_frame, textvariable=self.local_dir_var, width=30
        ).grid(row=1, column=1, sticky='ew', pady=2, padx=(0, 4))
        ttk.Button(
            self.local_frame, text="Browse...", command=self._browse_local_dir
        ).grid(row=1, column=2, sticky='w', pady=2)

        self.local_frame.columnconfigure(1, weight=1)

        # ---- Buttons -----------------------------------------------------
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side='bottom', pady=10)

        self.login_btn = ttk.Button(button_frame, text="Login", command=self._on_login)
        self.login_btn.pack(side='left', padx=5)
        ttk.Button(button_frame, text="Cancel", command=self._on_cancel).pack(side='left', padx=5)

        # Bind Enter key to login
        self.bind('<Return>', lambda e: self._on_login())

        # Store result (dict on success, None on cancel)
        self.result = None

        # Show the section that matches the chosen mode
        self._on_mode_change()

        # Set initial focus
        if self.mode_var.get() == 'remote' and self.username_var.get():
            self.password_entry.focus_set()

        # Wait for window to be closed
        self.wait_window()

    def _on_mode_change(self):
        """Show only the section relevant to the currently selected mode."""
        mode = self.mode_var.get()
        if mode == 'remote':
            self.local_frame.pack_forget()
            self.remote_frame.pack(fill='x', pady=4)
            self.title("MongoDB Login")
        else:
            self.remote_frame.pack_forget()
            self.local_frame.pack(fill='x', pady=4)
            self.title("Standalone Login")

    def _browse_local_dir(self):
        """Pick the folder used for the local JSON store."""
        initial = self.local_dir_var.get() or _default_local_data_dir()
        chosen = filedialog.askdirectory(
            parent=self,
            title="Select data folder",
            initialdir=initial if os.path.isdir(initial) else None,
        )
        if chosen:
            self.local_dir_var.set(chosen)

    def _on_login(self):
        """Handle login button click for either mode."""
        if self.mode_var.get() == 'local':
            data_dir = self.local_dir_var.get().strip()
            if not data_dir:
                messagebox.showerror("Error", "Please choose a data folder")
                return
            try:
                os.makedirs(data_dir, exist_ok=True)
            except OSError as exc:
                messagebox.showerror("Error", f"Cannot create folder:\n{exc}")
                return

            self.result = {'mode': 'local', 'data_dir': data_dir}
            self.parent.config['mode'] = 'local'
            self.parent.config['local_data_dir'] = data_dir
            # Standalone mode owns its own files, so admin actions are
            # always available; persist the flag for consistency.
            self.parent.config['admin_access'] = True
            self.parent._write_config()
            self.destroy()
            return

        # Remote (MongoDB) mode
        host_ip = self.host_ip_var.get().strip()
        port = self.port_var.get().strip()
        username = self.username_var.get().strip()
        password = self.password_var.get()
        auth_source = self.auth_source_var.get().strip()

        if not host_ip:
            messagebox.showerror("Error", "Please enter a host IP")
            return

        if not port:
            messagebox.showerror("Error", "Please enter a port number")
            return

        host = f"mongodb://{host_ip}:{port}"

        admin_access = bool(self.admin_access_var.get())

        self.result = {
            'mode': 'remote',
            'host': host,
            'username': username,
            'password': password,
            'auth_source': auth_source,
            'admin_access': admin_access,
        }
        self.parent.config.update({
            'mode': 'remote',
            'host_ip': host_ip,
            'port': port,
            'username': username,
            'auth_source': auth_source,
            'admin_access': admin_access,
        })
        self.parent._write_config()
        self.destroy()

    def _on_cancel(self):
        """Handle cancel button click"""
        self.result = None
        self.destroy()
