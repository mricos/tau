# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for tau - Terminal Audio Workstation

Build standalone app:
  pyinstaller tau.spec

Output: dist/tau (single executable)
"""

import sys
from pathlib import Path

block_cipher = None

# Collect all Python packages
a = Analysis(
    ['repl_py/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('engine/tau-engine', 'engine'),  # Include C engine binary
        ('engine/*.json', 'engine'),
    ],
    hiddenimports=[
        'tau_lib',
        'tau_lib.core',
        'tau_lib.core.state',
        'tau_lib.core.config',
        'tau_lib.core.commands_api',
        'tau_lib.core.project',
        'tau_lib.data',
        'tau_lib.data.data_loader',
        'tau_lib.data.trs',
        'tau_lib.integration',
        'tau_lib.integration.tau_playback',
        'repl_py',
        'repl_py.repl',
        'repl_py.cli',
        'tui_py',
        'tui_py.app',
        'tui_py.commands',
        'tui_py.content',
        'tui_py.rendering',
        'tui_py.ui',
        'curses',
        'readline',
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
    name='tau',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
