# -*- mode: python ; coding: utf-8 -*-
# TWZ Pdf — PyInstaller spec file
# Build command: pyinstaller build.spec

import os

block_cipher = None
base_dir = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    [os.path.join(base_dir, 'twz_pdf.py')],
    pathex=[base_dir],
    binaries=[],
    datas=[
        (os.path.join(base_dir, 'logo.ico'), '.'),
        (os.path.join(base_dir, 'try.jpg'), '.'),
    ],
    hiddenimports=[
        'pdf_to_image',
        'image_to_pdf',
        'pdf_crop',
        'pdf_split',
        'pdf_merge',
        'pdf_resize',
        'pdf_compress',
        'pdf_reorder',
        'pdf_magnifier',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'fitz',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'scipy', 'pandas',
        'sklearn', 'notebook', 'IPython',
    ],
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
    name='Towards Zero Error PDF Tool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(base_dir, 'logo.ico'),
)
