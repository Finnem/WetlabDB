# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# ``pymongo`` and ``bson`` are imported lazily inside try/except blocks
# (see wetlabdb/storage/ids.py and wetlabdb/storage/mongo.py), so PyInstaller
# can't see them via static analysis. Without this, the bundled EXE silently
# falls back to standalone-only mode and the "MongoDB server" radio in the
# login dialog is greyed out.
pymongo_datas, pymongo_binaries, pymongo_hiddenimports = collect_all('pymongo')
bson_datas, bson_binaries, bson_hiddenimports = collect_all('bson')

a = Analysis(
    ['wetlabDB.py'],
    pathex=[],
    binaries=[*pymongo_binaries, *bson_binaries],
    datas=[
        ('mongodb_config.json', '.'),
        *pymongo_datas,
        *bson_datas,
    ],
    hiddenimports=[
        *pymongo_hiddenimports,
        *bson_hiddenimports,
        *collect_submodules('rdkit.Chem'),
        'rdkit',
        'rdkit.Chem',
        'rdkit.Chem.Draw',
        'rdkit.Chem.AllChem',
        'rdkit.Chem.Draw.rdMolDraw2D',
        'pandas',
        'PIL',
        'PIL.ImageTk',
        # wetlabdb package layout (Phase 5/6 refactor).
        'wetlabdb',
        'wetlabdb.config',
        'wetlabdb.storage',
        'wetlabdb.storage.base',
        'wetlabdb.storage.ids',
        'wetlabdb.storage.json_codec',
        'wetlabdb.storage.local',
        'wetlabdb.storage.mongo',
        'wetlabdb.chem',
        'wetlabdb.chem.smiles',
        'wetlabdb.chem.similarity',
        'wetlabdb.chem.substructure',
        'wetlabdb.chem.enumerate',
        'wetlabdb.services',
        'wetlabdb.services.compounds',
        'wetlabdb.services.search',
        'wetlabdb.services.csv_io',
        'wetlabdb.ui',
        'wetlabdb.ui.app',
        'wetlabdb.ui.column_dialog',
        'wetlabdb.ui.json_form',
        'wetlabdb.ui.login_dialog',
        'wetlabdb.ui.molecule_cell',
        'wetlabdb.ui.molecule_editor',
        'wetlabdb.ui.molecule_treeview',
        'wetlabdb.ui.search_window',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='WetlabDB',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='wetlabDB_icon.ico',
) 