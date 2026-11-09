"""Builds the BatteryTray installer.

The result is a single ``BatteryTray-Setup-<version>.exe`` that the user can
run to install the app. It needs no extra runtime and no administrator
rights.

The build has three steps:

1. The application is compiled with PyInstaller into a one file executable.
2. The installer itself is compiled with PyInstaller as well. It carries the
   application in a ``payload`` folder.
3. Both are put into an installer image, and the installer executable is
   placed next to the payload so that it can copy itself out.

Run with::

    python build_installer.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build_installer"
DIST = ROOT / "release"
VERSION = "1.0.0"

APP_NAME = "BatteryTray"
APP_EXE = "BatteryTray.exe"
UNINSTALL_EXE = "uninstall.exe"


def run(command: list[str], cwd: Path | None = None) -> None:
    """Runs a command and stops when it fails."""
    print("$", " ".join(command))
    result = subprocess.run(command, cwd=cwd)
    if result.returncode != 0:
        raise SystemExit(f"命令失败：{' '.join(command)}")


def build_app() -> Path:
    """Compiles the application into a one file executable."""
    print("==> 编译主程序…")
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         "BatteryTray.spec"], cwd=ROOT)
    exe = ROOT / "dist" / APP_EXE
    if not exe.exists():
        raise SystemExit("主程序编译失败")
    return exe


def build_installer_exe(app_exe: Path | None = None) -> Path:
    """Compiles the installer into a one file executable.

    When the application is given, it is bundled into the installer, so
    the result is a single file that can be sent to somebody else.
    """
    print("==> 编译安装向导…")
    icon_value = str(ROOT / "assets" / "batterytray.ico")
    icon_value = icon_value.replace("\\", "/")

    bundled: list[str] = []
    if app_exe is not None:
        # The payload travels inside the installer as data files.
        bundled = [
            f"({str(app_exe)!r}, 'payload')",
            f"({str(ROOT / 'assets' / 'batterytray.ico')!r}, 'payload/assets')",
            f"({str(ROOT / 'assets' / 'batterytray.png')!r}, 'payload/assets')",
        ]
        readme = ROOT / "README.md"
        if readme.is_file():
            bundled.append(f"({str(readme)!r}, 'payload')")

    datas = ""
    if bundled:
        datas = "    datas=[\n" + "".join(
            f"        {item},\n" for item in bundled) + "    ],\n"
    else:
        datas = "    datas=[],\n"

    spec = BUILD / "installer.spec"
    spec.write_text(
        "# -*- mode: python ; coding: utf-8 -*-\n"
        '"""PyInstaller build script for the BatteryTray installer."""\n\n'
        "block_cipher = None\n\n"
        "a = Analysis(\n"
        "    ['installer_entry.py'],\n"
        f"    pathex=[{str(ROOT)!r}],\n"
        "    binaries=[],\n"
        f"{datas}"
        "    hiddenimports=[\n"
        "        'installer',\n"
        "        'installer.wizard',\n"
        "        'installer.payload',\n"
        "    ],\n"
        "    hookspath=[],\n"
        "    hooksconfig={},\n"
        "    runtime_hooks=[],\n"
        "    excludes=['matplotlib', 'numpy', 'pytest'],\n"
        "    win_no_prefer_redirects=False,\n"
        "    win_private_assemblies=False,\n"
        "    cipher=block_cipher,\n"
        "    noarchive=False,\n"
        ")\n\n"
        "pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)\n\n"
        "exe = EXE(\n"
        "    pyz,\n"
        "    a.scripts,\n"
        "    a.binaries,\n"
        "    a.zipfiles,\n"
        "    a.datas,\n"
        "    [],\n"
        "    name='BatteryTray-Setup',\n"
        "    debug=False,\n"
        "    bootloader_ignore_signals=False,\n"
        "    strip=False,\n"
        "    upx=True,\n"
        "    upx_exclude=[],\n"
        "    runtime_tmpdir=None,\n"
        "    console=False,\n"
        "    disable_windowed_traceback=False,\n"
        "    argv_emulation=False,\n"
        "    target_arch=None,\n"
        "    codesign_identity=None,\n"
        "    entitlements_file=None,\n"
        f"    icon={icon_value!r},\n"
        ")\n",
        encoding="utf-8")

    entry = BUILD / "installer_entry.py"
    entry.write_text(
        '"""Entry point for the BatteryTray installer."""\n\n'
        "from __future__ import annotations\n\n"
        "import sys\n\n"
        "from installer.wizard import main\n\n\n"
        "if __name__ == '__main__':\n"
        "    sys.exit(main())\n",
        encoding="utf-8")

    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         str(spec)], cwd=BUILD)
    exe = BUILD / "dist" / "BatteryTray-Setup.exe"
    if not exe.exists():
        raise SystemExit("安装向导编译失败")
    return exe


def make_portable(app_exe: Path) -> Path:
    """Packs the application into a zip as well.

    Some people prefer a portable copy over an installed one.
    """
    print("==> 生成便携版压缩包…")
    stage = BUILD / "portable"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    shutil.copy2(app_exe, stage / APP_EXE)
    assets = ROOT / "assets"
    if assets.is_dir():
        target = stage / "assets"
        target.mkdir()
        for item in assets.iterdir():
            if item.is_file():
                shutil.copy2(item, target / item.name)
    readme = ROOT / "README.md"
    if readme.exists():
        shutil.copy2(readme, stage / "README.md")

    DIST.mkdir(parents=True, exist_ok=True)
    archive = DIST / f"{APP_NAME}-{VERSION}-portable.zip"
    if archive.exists():
        archive.unlink()
    shutil.make_archive(
        str(archive.with_suffix("")), "zip", root_dir=stage, base_dir=".")
    shutil.rmtree(stage, ignore_errors=True)
    return archive


def main() -> None:
    BUILD.mkdir(exist_ok=True)
    app_exe = build_app()

    # The single file installer: the application travels inside it, so the
    # user only receives one file.
    print("==> 编译单文件安装包…")
    installer_exe = build_installer_exe(app_exe)
    DIST.mkdir(parents=True, exist_ok=True)
    setup = DIST / f"{APP_NAME}-Setup-{VERSION}.exe"
    if setup.exists():
        setup.unlink()
    shutil.copy2(installer_exe, setup)

    archive = make_portable(app_exe)

    print()
    print("打包完成：")
    print(f"  安装程序（单文件，可直接发送）  {setup}")
    print(f"  便携版                        {archive}")


if __name__ == "__main__":
    main()
