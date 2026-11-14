# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build script for BatteryTray."""

block_cipher = None

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        "batterytray.app",
        "batterytray.art",
        "batterytray.autostart",
        "batterytray.card",
        "batterytray.config",
        "batterytray.dpi",
        "batterytray.dwm",
        "batterytray.icon",
        "batterytray.singleton",
        "batterytray.quickpanel",
        "batterytray.window",
        "batterytray.renamedialog",
        "batterytray.mousesettingsdialog",
        "batterytray.drivers.razer",
        "batterytray.drivers.mouseconfig",
        "batterytray.drivers.asusmouse",
        "batterytray.drivers.mouseadapter",
        "batterytray.drivers.bluetooth",
        "win10toast",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "pytest",
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
    name="BatteryTray",
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
    icon="assets/batterytray.ico",
)
