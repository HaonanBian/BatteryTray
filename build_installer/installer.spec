# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build script for the BatteryTray installer."""

block_cipher = None

a = Analysis(
    ['installer_entry.py'],
    pathex=['D:\\Desktop\\a'],
    binaries=[],
    datas=[
        ('D:\\Desktop\\a\\dist\\BatteryTray.exe', 'payload'),
        ('D:\\Desktop\\a\\assets\\batterytray.ico', 'payload/assets'),
        ('D:\\Desktop\\a\\assets\\batterytray.png', 'payload/assets'),
        ('D:\\Desktop\\a\\README.md', 'payload'),
    ],
    hiddenimports=[
        'installer',
        'installer.wizard',
        'installer.payload',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pytest'],
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
    name='BatteryTray-Setup',
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
    icon='D:/Desktop/a/assets/batterytray.ico',
)
