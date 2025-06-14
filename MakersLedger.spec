# MakersLedger.spec (Updated)

# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['run_app.py'],  # Entry point is our wrapper
    pathex=[],
    binaries=[],
    datas=[
        # --- Add all your app's files and directories here ---
        ('main_app.py', '.'),
        ('models.py', '.'),
        ('config.yaml', '.'),
        ('database.py', '.'),
        
        # --- NEW: Bundle the entire 'utils' and 'app_pages' directories ---
        ('utils', 'utils'),
        ('app_pages', 'app_pages'),
        
        # Create an empty directory for file uploads within the app
        ('uploaded_files', 'uploaded_files')
    ],
    hiddenimports=[
        # --- Add libraries that might be hidden from PyInstaller ---
        'sqlalchemy.dialects.postgresql',
        'pandas',
        'plotly',
        'bcrypt',
        'streamlit_js_eval'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MakersLedger',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Keep True for debugging, change to False for final release
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)