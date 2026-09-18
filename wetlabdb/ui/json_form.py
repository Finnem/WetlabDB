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
from wetlabdb.schema.compound import compound_form


class JSONForm(tk.Frame):
    def __init__(self, master, initial=None, is_list=False, is_new_document=False, config=None):
        super().__init__(master)
        self.fields = []
        self.is_list = is_list
        self.config = config
        
        if is_new_document:
            # Create initial values from compound_form with proper types
            initial = {}
            for key, field_info in compound_form.items():
                field_type = field_info['type']
                default_value = field_info['default']
                
                # Convert default value to proper type
                if field_type == 'boolean':
                    initial[key] = bool(default_value)
                elif field_type == 'float':
                    initial[key] = float(default_value)
                elif field_type == 'file':
                    initial[key] = None
                else:  # string or dict
                    initial[key] = default_value
        elif initial is None:
            initial = {}
            
        self.build_form(initial)
        # Always add an empty field, whether it's a new document or editing
        self.add_empty_field()

    def build_form(self, data, parent=None):
        parent = parent or self
        self.parent = parent
        if isinstance(data, dict):
            for key, value in data.items():
                # Explicitly handle different types of values
                if isinstance(value, dict):
                    # Dictionary values need special handling
                    if 'filename' in value and 'data' in value:
                        # Handle file-like data
                        self.add_field(parent, key, value, field_type='file')
                    else:
                        # Regular dictionary - use dict field type
                        self.add_field(parent, key, value, field_type='dict')
                elif isinstance(value, bool):
                    # Boolean values
                    self.add_field(parent, key, value, field_type='boolean')
                elif isinstance(value, (int, float)):
                    # Numeric values
                    self.add_field(parent, key, value, field_type='float')
                elif isinstance(value, str) and value.startswith('{') and value.endswith('}'):
                    # String that might be a dictionary representation
                    dict_value = self._parse_dict_string(value)
                    if dict_value is not None:
                        # Successfully parsed as dictionary
                        self.add_field(parent, key, dict_value, field_type='dict')
                    else:
                        # Just a string that looks like a dictionary
                        self.add_field(parent, key, value)
                else:
                    # Default to string for other types
                    self.add_field(parent, key, value)
        else:
            self.add_field(parent, "", data)

    def add_empty_field(self, parent=None):
        parent = parent or self
        # Create a container frame for vertical stacking
        container = ttk.Frame(parent)
        container.pack(fill='x', pady=1)
        self.add_field(container, "", "")

    def add_field(self, parent, key="", value="", is_list=False, field_type=None):
        # Create a container frame for vertical stacking
        container = ttk.Frame(parent)
        container.pack(fill='x', pady=1)
        
        # Create a frame for the field content
        row = ttk.Frame(container)
        row.pack(fill='x', pady=2)
        
        # Configure grid weights
        row.grid_columnconfigure(2, weight=1)  # Make value column expandable
        
        # Key entry
        key_entry = ttk.Entry(row, width=30)
        key_entry.insert(0, key)
        key_entry.grid(row=0, column=0, padx=2, sticky='w')

        # Determine the field type if not explicitly provided
        if field_type is None:
            # Get field type from compound_form if it exists
            if key in compound_form:
                field_type = compound_form[key]['type']
            # Determine from value type
            elif isinstance(value, bool):
                field_type = 'boolean'
            elif isinstance(value, (int, float)):
                field_type = 'float'
            elif isinstance(value, dict):
                if 'filename' in value and 'data' in value:
                    field_type = 'file'
                else:
                    field_type = 'dict'
            elif isinstance(value, str) and value.startswith('{') and value.endswith('}'):
                # Try to parse as dictionary
                parsed_dict = self._parse_dict_string(value)
                if parsed_dict is not None:
                    field_type = 'dict'
                    value = parsed_dict  # Update value to be the actual dict
                else:
                    field_type = 'string'
            else:
                field_type = 'string'  # default type

        # Create the type variable and menu
        type_var = tk.StringVar(value=field_type)
        type_menu = ttk.OptionMenu(row, type_var, field_type, 'string', 'float', 'boolean', 'dict', 'file',
                                 command=lambda x: self._on_type_change(x, key_entry, type_var, val_frame))
        type_menu.grid(row=0, column=1, padx=2)

        # Value frame - use grid to allow expansion
        val_frame = ttk.Frame(row)
        val_frame.grid(row=0, column=2, sticky='ew', padx=2)
        val_frame.grid_columnconfigure(0, weight=1)

        # Create initial value widget based on type
        self._create_value_widget(val_frame, field_type, value, key_entry, type_var)

    def _on_type_change(self, new_type, key_entry, type_var, val_frame):
        """Handle type change in the dropdown menu"""
        # Clear the value frame
        for widget in val_frame.winfo_children():
            widget.destroy()
        
        # Create new widget for the selected type
        self._create_value_widget(val_frame, new_type, "", key_entry, type_var)

    def _create_value_widget(self, parent, field_type, value, key_entry, type_var):
        """Create the appropriate widget based on field type"""
        parent.grid_columnconfigure(0, weight=1)  # Make value widgets expandable
        
        if field_type == 'boolean':
            val_entry = ttk.Checkbutton(parent)
            if value:
                val_entry.state(['selected'])
            else:
                val_entry.state(['!selected'])
            val_entry.grid(row=0, column=0, sticky='ew')
            self.fields.append((key_entry, type_var, val_entry))
        elif field_type == 'file':
            file_frame = ttk.Frame(parent)
            file_frame.grid(row=0, column=0, sticky='ew')
            file_frame.grid_columnconfigure(0, weight=1)
            
            # For file fields, just display the path string directly
            display_value = str(value) if value else ""
            
            filename_var = tk.StringVar(value=display_value)
            filename_entry = ttk.Entry(file_frame, textvariable=filename_var, state='readonly')
            filename_entry.grid(row=0, column=0, sticky='ew')
            
            select_btn = ttk.Button(file_frame, text="Select File", 
                                 command=lambda: self._select_file(filename_var, file_data_var))
            select_btn.grid(row=0, column=1, padx=(2, 0))
            
            # Store the path string
            file_data_var = tk.StringVar(value=display_value)
            self.fields.append((key_entry, type_var, (filename_var, file_data_var)))
        elif field_type == 'dict':
            # Create a frame for the dictionary content with visual distinction
            dict_frame = ttk.Frame(parent, relief="groove", borderwidth=2)
            dict_frame.grid(row=0, column=0, sticky='ew', padx=2, pady=2)
            dict_frame.grid_columnconfigure(0, weight=1)
            
            # Add a label at the top to indicate it's a dictionary
            dict_label = ttk.Label(dict_frame, text="Dictionary", foreground="blue")
            dict_label.pack(fill='x', padx=2, pady=(2,0))
            
            # Create a frame for the dictionary fields
            fields_frame = ttk.Frame(dict_frame)
            fields_frame.pack(fill='x', expand=True, padx=5)
            
            # Initialize _dict_fields attribute to store field references
            fields_frame._dict_fields = []
            fields_frame._new_field_added = False
            
            # Process value to ensure it's a proper dictionary
            dict_value = value
            if isinstance(value, str):
                # Try to parse as dictionary using our helper
                parsed_dict = self._parse_dict_string(value)
                if parsed_dict is not None:
                    dict_value = parsed_dict
                else:
                    dict_value = {}
            elif not isinstance(value, dict):
                dict_value = {}
                
            # If we have existing dictionary data, create fields for it
            if isinstance(dict_value, dict):
                for k, v in dict_value.items():
                    self._add_dict_field(fields_frame, key_entry, type_var, k, v)
            
            # Add an empty field
            self._add_dict_field(fields_frame, key_entry, type_var)
            
            self.fields.append((key_entry, type_var, fields_frame))
        else:  # string or float
            val_entry = ttk.Entry(parent)
            val_entry.insert(0, str(value))
            val_entry.grid(row=0, column=0, sticky='ew')
            self.fields.append((key_entry, type_var, val_entry))

            def on_value_change(*args):
                if isinstance(val_entry, ttk.Entry) and val_entry.get().strip() and self.fields[-1] == (key_entry, type_var, val_entry):
                    parent_frame = parent.master.master
                    self.add_empty_field(parent_frame)

            if isinstance(val_entry, ttk.Entry):
                val_entry.bind('<KeyRelease>', on_value_change)

    def _add_dict_field(self, parent, parent_key_entry, parent_type_var, key="", value=""):
        """Add a new key-value pair to a dictionary field"""
        # Create a container frame for vertical stacking
        container = ttk.Frame(parent)
        container.pack(fill='x', pady=1)
        
        # Create a frame for the field content
        field_frame = ttk.Frame(container)
        field_frame.pack(fill='x', pady=1)
        
        # Key entry
        key_entry = ttk.Entry(field_frame, width=25)  # Increased width from 20 to 25
        key_entry.insert(0, key)
        key_entry.pack(side='left', padx=2)
        
        # Determine appropriate field type based on value
        field_type = 'string'  # Default type
        if isinstance(value, bool):
            field_type = 'boolean'
        elif isinstance(value, (int, float)):
            field_type = 'float'
        elif isinstance(value, dict):
            field_type = 'dict'
        elif isinstance(value, str):
            # Check if the string might be a dictionary representation
            parsed_dict = self._parse_dict_string(value)
            if parsed_dict is not None:
                field_type = 'dict'
                value = parsed_dict  # Update value to be the actual dict
            elif value.lower() in ('true', 'false'):
                field_type = 'boolean'
                value = value.lower() == 'true'
            elif value.replace('.', '', 1).isdigit():
                field_type = 'float'
                try:
                    value = float(value)
                except ValueError:
                    field_type = 'string'
        
        # Type selection for the value
        type_var = tk.StringVar(value=field_type)
        type_menu = ttk.OptionMenu(field_frame, type_var, field_type, 'string', 'float', 'boolean', 'dict', 'file',
                                 command=lambda x: self._on_dict_type_change(x, key_entry, type_var, val_frame))
        type_menu.pack(side='left', padx=2)
        
        # Value frame
        val_frame = ttk.Frame(field_frame)
        val_frame.pack(side='left', fill='x', expand=True, padx=2)
        
        # Create the appropriate widget based on field type
        if field_type == 'dict' and isinstance(value, dict):
            # For dictionary type with actual dictionary value, create a nested structure
            nested_frame = ttk.Frame(val_frame, relief="groove", borderwidth=1)
            nested_frame.pack(fill='x', expand=True)
            
            # Add a label to indicate it's a nested dictionary
            dict_label = ttk.Label(nested_frame, text="Nested Dict", foreground="blue", font=('Arial', 8))
            dict_label.pack(fill='x', padx=2, pady=(0,0))
            
            # Create a frame for the dictionary fields
            fields_frame = ttk.Frame(nested_frame)
            fields_frame.pack(fill='x', expand=True, padx=3)
            
            # Initialize attributes
            fields_frame._dict_fields = []
            fields_frame._new_field_added = False
            
            
            # Add fields for each key-value pair in the dictionary
            for k, v in value.items():
                self._add_dict_field(fields_frame, key_entry, type_var, k, v)
            
            # Add an empty field for new entries
            self._add_dict_field(fields_frame, key_entry, type_var)
            
            # Store reference to the fields frame
            val_frame._dict_frame = fields_frame
        else:
            # For other types, create the appropriate widget
            self._create_value_widget(val_frame, field_type, value, key_entry, type_var)
        
        # Delete button
        del_btn = ttk.Button(field_frame, text="x", width=2,
                           command=lambda: container.destroy())
        del_btn.pack(side='left', padx=2)
        
        # Store the field reference
        if not hasattr(parent, '_dict_fields'):
            parent._dict_fields = []
            parent._new_field_added = False  # Add flag to track if a new field was just added
        parent._dict_fields.append((key_entry, type_var, val_frame))

        # Auto-add new field when both key and value are filled
        def check_and_add_new_field(*args):
            # Skip if this is not the last field or if we've already added a new field
            if parent._dict_fields[-1] != (key_entry, type_var, val_frame) or parent._new_field_added:
                return
                
            # Check if both key and value are filled
            key_filled = bool(key_entry.get().strip())
            
            # Check the value based on field type
            value_filled = False
            current_type = type_var.get()
            
            if current_type == 'boolean':
                # For boolean, assume it's filled
                value_filled = True
            elif current_type == 'dict':
                # For dictionary, check if it has any items
                if hasattr(val_frame, '_dict_frame') and val_frame._dict_frame._dict_fields:
                    # Check if at least one field in the nested dictionary has both key and value
                    for nested_k_entry, _, _ in val_frame._dict_frame._dict_fields[:-1]:  # Skip the last empty field
                        if nested_k_entry.get().strip():
                            value_filled = True
                            break
            else:
                # For other types, check if the entry has text
                for widget in val_frame.winfo_children():
                    if isinstance(widget, ttk.Entry) and widget.get().strip():
                        value_filled = True
                        break
            
            # If both key and value are filled, add a new field
            if key_filled and value_filled:
                # Mark that we've added a new field to prevent multiple additions
                parent._new_field_added = True
                self._add_dict_field(parent, parent_key_entry, parent_type_var)

        # Bind key entry change event
        key_entry.bind('<KeyRelease>', check_and_add_new_field)
        
        # Bind value change events to appropriate widgets
        if field_type != 'dict':
            for widget in val_frame.winfo_children():
                if isinstance(widget, (ttk.Entry, ttk.Checkbutton)):
                    widget.bind('<KeyRelease>', check_and_add_new_field)
                    # For checkbuttons, also bind to virtual events
                    if isinstance(widget, ttk.Checkbutton):
                        widget.bind('<<CheckbuttonToggled>>', check_and_add_new_field)

    def _on_dict_type_change(self, new_type, key_entry, type_var, val_frame):
        """Handle type change in dictionary field"""
        # Clear the value frame
        for widget in val_frame.winfo_children():
            widget.destroy()
        
        # Get current value if possible
        current_value = None
        if hasattr(val_frame, '_dict_frame'):
            # Get dictionary value from the nested frame
            current_value = self._get_dict_value(val_frame._dict_frame)
        
        # Create new widget for the selected type
        if new_type == 'dict':
            # Create a frame for the dictionary fields
            dict_frame = ttk.Frame(val_frame)
            dict_frame.pack(fill='x', expand=True)
            
            # Initialize the nested dictionary structure
            dict_frame._dict_fields = []
            dict_frame._new_field_added = False
            
            # If we have a current dictionary value, use it
            if isinstance(current_value, dict) and current_value:
                for k, v in current_value.items():
                    self._add_dict_field(dict_frame, key_entry, type_var, k, v)
            
            # Add an empty field
            self._add_dict_field(dict_frame, key_entry, type_var)
            
            # Store the frame reference
            val_frame._dict_frame = dict_frame
        else:
            # Convert dictionary to string if changing from dict to another type
            value = ""
            if isinstance(current_value, dict) and current_value:
                try:
                    value = json.dumps(current_value)
                except Exception as e:
                    # Silently handle error
                    pass
            
            # Create appropriate widget for the new type
            self._create_value_widget(val_frame, new_type, value, key_entry, type_var)

    def _select_file(self, filename_var, file_data_var):
        file_path = filedialog.askopenfilename()
        if file_path:
            try:
                # Normalize path separators and split
                normalized_path = file_path.replace('\\', '/').replace('//', '/')
                path_parts = normalized_path.split('/')
                
                try:
                    # Find the last occurrence of "Databases" in the path
                    databases_index = len(path_parts) - 1 - path_parts[::-1].index("Databases")
                    # Get the relative path starting from "Databases"
                    relative_path = '/'.join(["Databases"] + path_parts[databases_index + 1:])
                    
                    # Create file info dictionary
                    file_info = {
                        'filename': os.path.basename(file_path),
                        'data': relative_path,
                        'owner': (self.config.get('username', '') if hasattr(self, 'config') and isinstance(self.config, dict) else ""),
                        'upload_time': datetime.now().isoformat()
                    }
                    
                    # Update the display and stored value
                    filename_var.set(relative_path)
                    file_data_var.set(json.dumps(file_info))
                except ValueError:
                    messagebox.showerror("Error", "Selected file must be under a 'Databases' directory")
            except Exception as e:
                messagebox.showerror("Error", f"Could not process file: {str(e)}")

    def to_json(self):
        """Convert form data to JSON-compatible dictionary with proper type handling"""
        if self.is_list:
            return [field[2].to_json() if isinstance(field[2], JSONForm) else self._get_field_value(field) for field in self.fields]
        else:
            result = {}
            dict_fields = {}  # Keep track of dictionary fields for post-processing
            
            # Process all fields
            for key_entry, type_var, value_widget in self.fields:
                try:
                    key = key_entry.get().strip()
                    if not key:  # Skip empty keys
                        continue
                    
                    # Get the value based on field type
                    field_type = type_var.get()
                    
                    if isinstance(value_widget, JSONForm):
                        result[key] = value_widget.to_json()
                    elif field_type == 'dict' and isinstance(value_widget, ttk.Frame) and hasattr(value_widget, '_dict_fields'):
                        # Process dictionary field
                        dict_value = self._get_dict_value(value_widget)
                        if dict_value:  # Only include non-empty dictionaries
                            dict_fields[key] = dict_value
                            result[key] = dict_value
                    else:
                        # Get the value for regular fields
                        value = self._get_field_value((key_entry, type_var, value_widget))
                        
                        # Special handling for potential dictionary strings
                        if isinstance(value, str) and value.startswith('{') and value.endswith('}'):
                            parsed_dict = self._parse_dict_string(value)
                            if parsed_dict is not None:
                                # If it's a dictionary, store it for special processing
                                dict_fields[key] = parsed_dict
                                result[key] = parsed_dict
                            else:
                                result[key] = value
                        else:
                            result[key] = value
                except Exception as e:
                    print(f"Error processing field {key}: {e}")
                    continue
            
            # Post-process to clean up duplicated data and ensure proper dictionary handling
            if dict_fields:
                # Find keys that match dictionary entries
                keys_to_remove = []
                for dict_key, dict_value in dict_fields.items():
                    if not isinstance(dict_value, dict):
                        continue
                        
                    for k, v in dict_value.items():
                        # Check if a top-level key matches a nested dictionary entry
                        if k in result and k != dict_key:
                            # Verify the values match 
                            nested_value = dict_value[k]
                            if nested_value == result[k]:
                                keys_to_remove.append(k)
                
                # Remove duplicated keys
                for k in keys_to_remove:
                    if k in result:
                        del result[k]
            
            # Ensure proper type handling for compound form fields
            if 'Name' in result:  # This is likely a compound document
                for field_name, config in compound_form.items():
                    if field_name in result:
                        field_type = config['type']
                        # Convert to proper type if needed
                        if field_type == 'boolean' and not isinstance(result[field_name], bool):
                            if isinstance(result[field_name], str):
                                result[field_name] = result[field_name].lower() in ('true', 'yes', '1', 't')
                            else:
                                result[field_name] = bool(result[field_name])
                        elif field_type == 'float' and not isinstance(result[field_name], float):
                            try:
                                result[field_name] = float(result[field_name])
                            except (ValueError, TypeError):
                                result[field_name] = 0.0
                        elif field_type == 'dict' and isinstance(result[field_name], str):
                            # Try to parse dictionary string
                            parsed_dict = self._parse_dict_string(result[field_name])
                            if parsed_dict is not None:
                                result[field_name] = parsed_dict
            
            return result

    def _get_field_value(self, field):
        key_entry, type_var, value_widget = field
        field_type = type_var.get()
        
        if field_type == 'boolean':
            return bool(value_widget.instate(['selected']))
        elif field_type == 'float':
            try:
                return float(value_widget.get())
            except ValueError:
                return 0.0
        elif field_type == 'file':
            filename_var, file_data_var = value_widget
            if filename_var.get() and file_data_var.get():
                try:
                    # Try to parse as JSON first (new format with owner info)
                    file_info = json.loads(file_data_var.get())
                    return file_info
                except json.JSONDecodeError:
                    # Fall back to old format
                    return {
                        'filename': filename_var.get(),
                        'data': file_data_var.get()
                    }
            return None
        elif field_type == 'dict':
            # Handle dictionary fields
            if isinstance(value_widget, ttk.Frame) and hasattr(value_widget, '_dict_fields'):
                dict_value = {}
                for k_entry, t_var, v_widget in value_widget._dict_fields:
                    try:
                        k = k_entry.get().strip()
                        if k:  # Only include non-empty keys
                            field_type = t_var.get()
                            if field_type == 'boolean':
                                for child in v_widget.winfo_children():
                                    if isinstance(child, ttk.Checkbutton):
                                        dict_value[k] = bool(child.instate(['selected']))
                                        break
                            elif field_type == 'float':
                                for child in v_widget.winfo_children():
                                    if isinstance(child, ttk.Entry):
                                        try:
                                            dict_value[k] = float(child.get())
                                        except ValueError:
                                            dict_value[k] = 0.0
                                        break
                            elif field_type == 'dict':
                                if isinstance(v_widget, ttk.Frame) and hasattr(v_widget, '_dict_fields'):
                                    # Handle nested dictionaries
                                    dict_value[k] = self._get_dict_value(v_widget)
                            else:  # string or default
                                for child in v_widget.winfo_children():
                                    if isinstance(child, ttk.Entry):
                                        value = child.get()
                                        # Try to parse as dictionary
                                        parsed_dict = self._parse_dict_string(value)
                                        if parsed_dict is not None:
                                            dict_value[k] = parsed_dict
                                            continue
                                        dict_value[k] = value
                                        break
                    except Exception as e:
                        print(f"Error processing dictionary field {k}: {e}")
                        continue
                return dict_value
            return {}
        else:  # string
            if isinstance(value_widget, JSONForm):
                return value_widget.to_json()
            value = value_widget.get()
            
            # Try to parse as dictionary
            parsed_dict = self._parse_dict_string(value)
            if parsed_dict is not None:
                return parsed_dict
            
            # Canonicalize SMILES if this is the SMILES field
            if key_entry.get().strip() == 'SMILES' and value.strip():
                try:
                    mol = Chem.MolFromSmiles(value)
                    if mol:
                        return Chem.MolToSmiles(mol, canonical=True)
                except Exception as e:
                    print(f"Error canonicalizing SMILES: {e}")
            return value

    def _get_dict_value(self, dict_frame):
        """Get the value of a dictionary field"""
        result = {}
        try:
            for k_entry, t_var, v_widget in dict_frame._dict_fields:
                try:
                    k = k_entry.get().strip()
                    if not k:  # Skip empty keys
                        continue
                        
                    field_type = t_var.get()
                    if field_type == 'boolean':
                        for child in v_widget.winfo_children():
                            if isinstance(child, ttk.Checkbutton):
                                result[k] = bool(child.instate(['selected']))
                                break
                    elif field_type == 'float':
                        for child in v_widget.winfo_children():
                            if isinstance(child, ttk.Entry):
                                try:
                                    result[k] = float(child.get())
                                except ValueError:
                                    result[k] = 0.0
                                break
                    elif field_type == 'dict':
                        # Handle nested dictionaries - find the fields frame within the value widget
                        nested_frame = None
                        for child in v_widget.winfo_children():
                            if isinstance(child, ttk.Frame) and hasattr(child, '_dict_fields'):
                                nested_frame = child
                                break
                            
                        if nested_frame is None:
                            # If we couldn't find the nested frame directly, look one level deeper
                            for child in v_widget.winfo_children():
                                if isinstance(child, ttk.Frame):
                                    for subchild in child.winfo_children():
                                        if isinstance(subchild, ttk.Frame) and hasattr(subchild, '_dict_fields'):
                                            nested_frame = subchild
                                            break
                                    if nested_frame:
                                        break
                            
                        if nested_frame:
                            # Process the nested dictionary
                            nested_dict = self._get_dict_value(nested_frame)
                            if nested_dict:  # Only add if the nested dict is not empty
                                result[k] = nested_dict
                        else:
                            print(f"Warning: Could not find nested frame for dictionary field: {k}")
                    else:  # string or default
                        for child in v_widget.winfo_children():
                            if isinstance(child, ttk.Entry):
                                value = child.get()
                                # Try to parse as dictionary if it looks like one
                                if value and value.startswith('{') and value.endswith('}'):
                                    parsed_dict = self._parse_dict_string(value)
                                    if parsed_dict is not None:
                                        result[k] = parsed_dict
                                        break
                                # Try to convert to appropriate type
                                if value.lower() == 'true':
                                    result[k] = True
                                elif value.lower() == 'false':
                                    result[k] = False
                                elif value.isdigit():
                                    result[k] = int(value)
                                else:
                                    try:
                                        result[k] = float(value)
                                    except ValueError:
                                        result[k] = value
                                break
                except Exception as e:
                    print(f"Error processing nested dictionary field {k}: {e}")
                    continue
        except Exception as e:
            print(f"Error processing dictionary frame: {e}")
        
        return result

    def _parse_dict_string(self, value_str):
        """Parse a string that may contain a dictionary representation in Python or JSON format"""
        if not value_str or not isinstance(value_str, str):
            return None
            
        # Strip any whitespace
        value_str = value_str.strip()
        
        # Check if it looks like a dictionary
        if not (value_str.startswith('{') and value_str.endswith('}')):
            return None
            
        # Try parsing as JSON first
        try:
            return json.loads(value_str)
        except json.JSONDecodeError as e:
            print(f"Failed to parse as JSON: {e}")
            pass
            
        # If JSON parsing fails, try converting Python dict format to JSON
        try:
            # Replace Python single quotes with double quotes for JSON
            # This is a simple approach and may not work for all cases
            # First replace double quotes that are already there with a placeholder
            value_str = value_str.replace('\\"', '___DOUBLEQUOTE___')
            value_str = value_str.replace('\\"', '___DOUBLEQUOTE___')
            
            # Replace None with null for JSON compatibility
            value_str = value_str.replace("None", "null")
            
            # Replace True/False with proper JSON booleans
            value_str = value_str.replace("True", "true")
            value_str = value_str.replace("False", "false")
            
            # Then replace single quotes with double quotes
            value_str = value_str.replace("'", '"')
            
            # Restore any escaped double quotes
            value_str = value_str.replace('___DOUBLEQUOTE___', '\\"')
            
            # Try parsing the modified string
            return json.loads(value_str)
        except Exception as e:
            print(f"Failed to parse Python dict string: {value_str} - {e}")
            
            # Last resort: try using ast.literal_eval which can parse Python literals safely
            try:
                import ast
                return ast.literal_eval(value_str)
            except Exception as e:
                print(f"Failed to parse with ast.literal_eval: {e}")
                return None
