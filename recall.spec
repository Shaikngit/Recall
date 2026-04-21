# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Recall KB desktop companion."""

import os
import customtkinter

block_cipher = None

ctk_path = os.path.dirname(customtkinter.__file__)

a = Analysis(
    ['kb_app/tray.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Flask templates & static files
        ('kb_app/templates', 'kb_app/templates'),
        ('kb_app/static', 'kb_app/static'),
        # Cloud config (place next to exe)
        ('.recall-config.json', '.'),
        # CustomTkinter assets (themes, fonts, images)
        (ctk_path, 'customtkinter'),
    ],
    hiddenimports=[
        'kb_app',
        'kb_app.app',
        'kb_app.ai',
        'kb_app.blob_content',
        'kb_app.core',
        'kb_app.tray',
        'werkzeug',
        'werkzeug.serving',
        'flask',
        'pystray',
        'pystray._win32',
        'pynput',
        'pynput.keyboard',
        'pynput.keyboard._win32',
        'PIL',
        'PIL.ImageGrab',
        'requests',
        'customtkinter',
        'winotify',
        'speech_recognition',
        'pyaudio',
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
    [],
    exclude_binaries=True,
    name='RecallKB',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # No console window — tray + GUI only
    icon='kb_app/static/recall.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RecallKB',
)
