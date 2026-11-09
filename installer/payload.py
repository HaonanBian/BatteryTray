"""Installation helpers for BatteryTray.

The installer is written from scratch so that it needs no external tool and
runs without administrator rights. It copies the application into the chosen
folder, creates the shortcuts and registers the uninstaller with Windows, so
the app shows up in "Apps and features" and can be removed from there.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

APP_NAME = "BatteryTray"
APP_VERSION = "1.0.0"
PUBLISHER = "BatteryTray"

# The per-user uninstall entry. It lives under HKEY_CURRENT_USER, so no
# administrator rights are needed to install or to remove the app.
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\BatteryTray"


def resources_dir() -> Path:
    """The folder that holds the bundled files.

    For the frozen installer this is the folder PyInstaller unpacks the
    embedded files into, so the payload travels inside the executable and
    the user only has to copy a single file around.
    """
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def payload_dir() -> Path:
    """The folder that holds the files to install."""
    base = resources_dir()
    candidate = base / "payload"
    if candidate.is_dir():
        return candidate
    # Fall back to the folder the executable sits in, which is how the
    # folder based build works.
    if getattr(sys, "frozen", False):
        candidate = Path(sys.executable).resolve().parent / "payload"
        if candidate.is_dir():
            return candidate
    return base


def default_install_dir() -> Path:
    """The folder the app is installed into by default.

    The per-user programs folder is used on purpose: it needs no
    administrator rights, and the app keeps working when it is moved to
    another machine.
    """
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "Programs" / APP_NAME


def startup_dir() -> Path:
    """The Startup folder, where the autostart shortcut goes."""
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def start_menu_dir() -> Path:
    """The Start Menu programs folder."""
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def desktop_dir() -> Path:
    """The desktop folder."""
    base = os.environ.get("USERPROFILE") or str(Path.home())
    return Path(base) / "Desktop"


def config_dir() -> Path:
    """The folder that holds the settings."""
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / APP_NAME


# --------------------------------------------------------------------------
# Shortcuts
# --------------------------------------------------------------------------


def create_shortcut(shortcut: Path, target: str, arguments: str = "",
                    working_dir: str = "", description: str = "",
                    icon: str = "") -> bool:
    """Writes a .lnk file.

    The values are handed to PowerShell through the environment, so a path
    with spaces or quotes cannot break the script. The target must not be
    quoted; Windows stores it as a plain path and drops a quoted one.
    """
    try:
        shortcut.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False

    env = dict(os.environ)
    env["LNK_PATH"] = str(shortcut)
    env["LNK_TARGET"] = target
    env["LNK_ARGS"] = arguments
    env["LNK_WORKDIR"] = working_dir or str(shortcut.parent)
    env["LNK_DESC"] = description
    env["LNK_ICON"] = icon

    script = (
        "$s = (New-Object -ComObject WScript.Shell)"
        ".CreateShortcut($env:LNK_PATH);"
        "$s.TargetPath = $env:LNK_TARGET;"
        "$s.Arguments = $env:LNK_ARGS;"
        "$s.WorkingDirectory = $env:LNK_WORKDIR;"
        "$s.Description = $env:LNK_DESC;"
        "if ($env:LNK_ICON -ne '') { $s.IconLocation = $env:LNK_ICON };"
        "$s.Save()"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=30, env=env)
    except (subprocess.SubprocessError, OSError):
        return False
    return result.returncode == 0 and shortcut.exists()


def delete_shortcut(shortcut: Path) -> bool:
    """Removes a .lnk file."""
    try:
        if shortcut.exists():
            shortcut.unlink()
    except OSError:
        return False
    return True


def shortcut_target(shortcut: Path) -> str:
    """The target of a shortcut, used to check that it still works."""
    if not shortcut.exists():
        return ""
    env = dict(os.environ)
    env["LNK_PATH"] = str(shortcut)
    script = (
        "$s = (New-Object -ComObject WScript.Shell)"
        ".CreateShortcut($env:LNK_PATH);"
        "$s.TargetPath"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=30, env=env)
    except (subprocess.SubprocessError, OSError):
        return ""
    return result.stdout.decode(errors="replace").strip()


# --------------------------------------------------------------------------
# The registry
# --------------------------------------------------------------------------


def register_uninstall(install_dir: Path, exe_name: str = "BatteryTray.exe") -> None:
    """Adds the app to "Apps and features"."""
    import winreg

    uninstaller = install_dir / "uninstall.exe"
    key = winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, 0, winreg.KEY_WRITE)
    try:
        icon = install_dir / exe_name
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, PUBLISHER)
        winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, str(icon))
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(install_dir))
        winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ,
                          f'"{uninstaller}"')
        winreg.SetValueEx(key, "QuietUninstallString", 0, winreg.REG_SZ,
                          f'"{uninstaller}" /quiet')
        winreg.SetValueEx(key, "InstallDate", 0, winreg.REG_SZ,
                          __import__("datetime").datetime.now().strftime("%Y%m%d"))
        # The app has no settings of its own in the installer, so Windows
        # should not offer a repair or a modify button.
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
    finally:
        key.Close()


def unregister_uninstall() -> None:
    """Removes the app from "Apps and features"."""
    import winreg

    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except OSError:
        pass


def is_installed() -> bool:
    """Whether the app is registered as installed."""
    import winreg

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except OSError:
        return False
    key.Close()
    return True


def installed_location() -> Path | None:
    """The folder the app was installed into."""
    import winreg

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except OSError:
        return None
    try:
        value, _type = winreg.QueryValueEx(key, "InstallLocation")
    except OSError:
        return None
    finally:
        key.Close()
    return Path(value)


# --------------------------------------------------------------------------
# Installing and removing
# --------------------------------------------------------------------------


def stop_running_app() -> None:
    """Closes a running copy of the app.

    The files cannot be overwritten while the program holds them open.
    """
    for name in ("BatteryTray.exe",):
        try:
            subprocess.run(["taskkill", "/F", "/IM", name],
                           capture_output=True, timeout=15)
        except (subprocess.SubprocessError, OSError):
            pass

    # Windows needs a moment to release the file handles, so wait until
    # the executable can be opened for writing again.
    target = default_install_dir() / "BatteryTray.exe"
    for _ in range(20):
        if not target.exists():
            return
        try:
            with open(target, "r+b"):
                return
        except OSError:
            time.sleep(0.5)


def uninstaller_source() -> Path:
    """The file that gets installed as the uninstaller.

    In the single file build the installer executable is its own
    uninstaller, so it is copied instead of a separate file. The running
    executable is the original file, not the copy PyInstaller unpacks into
    the temporary folder, so the path comes from the first argument.
    """
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            bundled = Path(meipass) / "payload" / "uninstall.exe"
            if bundled.is_file():
                return bundled
        # The installer is its own uninstaller. Copy the original file, not
        # the unpacked one in the temporary folder.
        original = sys.argv[0] if sys.argv else ""
        if original:
            candidate = Path(original).resolve()
            if candidate.is_file():
                return candidate
        return Path(sys.executable).resolve()
    return Path(__file__).resolve().parent.parent / "installer" / "uninstall.exe"


def _copy_with_retry(source: Path, target: Path, attempts: int = 10) -> bool:
    """Copies a file and waits if Windows still holds the old one open.

    A running copy of the app keeps its own executable locked for a short
    moment after it was killed, so the copy is retried a few times.
    """
    for attempt in range(attempts):
        try:
            shutil.copy2(source, target)
            return True
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.5)
        except OSError:
            return False
    return False


def install(install_dir: Path, desktop_shortcut: bool = True,
            autostart: bool = False, progress=None) -> list[str]:
    """Copies the app into place and wires everything up.

    Returns the list of actions that were carried out.
    """
    actions: list[str] = []
    source = payload_dir()
    install_dir = Path(install_dir)

    def report(message: str) -> None:
        actions.append(message)
        if progress is not None:
            progress(message)

    stop_running_app()

    report("正在创建安装目录…")
    install_dir.mkdir(parents=True, exist_ok=True)

    report("正在复制程序文件…")
    for name in ("BatteryTray.exe", "README.md"):
        candidate = source / name
        if candidate.is_file():
            _copy_with_retry(candidate, install_dir / name)
    # The uninstaller may be the installer itself in the single file build.
    uninstaller = uninstaller_source()
    if uninstaller.is_file():
        _copy_with_retry(uninstaller, install_dir / "uninstall.exe")

    # The icon is used for the shortcuts and the task bar.
    assets = source / "assets"
    if assets.is_dir():
        target_assets = install_dir / "assets"
        target_assets.mkdir(parents=True, exist_ok=True)
        for item in assets.iterdir():
            if item.is_file():
                shutil.copy2(item, target_assets / item.name)

    exe = install_dir / "BatteryTray.exe"
    icon = str(install_dir / "assets" / "batterytray.ico")
    if not Path(icon).exists():
        icon = str(exe)

    report("正在创建开始菜单快捷方式…")
    create_shortcut(
        start_menu_dir() / APP_NAME / f"{APP_NAME}.lnk",
        target=str(exe), working_dir=str(install_dir),
        description=f"{APP_NAME} - 鼠标与耳机电量", icon=icon)

    if desktop_shortcut:
        report("正在创建桌面快捷方式…")
        create_shortcut(
            desktop_dir() / f"{APP_NAME}.lnk",
            target=str(exe), working_dir=str(install_dir),
            description=f"{APP_NAME} - 鼠标与耳机电量", icon=icon)

    if autostart:
        report("正在设置开机自启…")
        create_shortcut(
            startup_dir() / f"{APP_NAME}.lnk",
            target=str(exe), working_dir=str(install_dir),
            description=f"{APP_NAME} - 开机自启", icon=icon)

    report("正在写入注册表…")
    register_uninstall(install_dir)

    return actions


def uninstall(install_dir: Path, remove_settings: bool = False,
              progress=None) -> list[str]:
    """Removes the app again.

    Returns the list of actions that were carried out.
    """
    actions: list[str] = []
    install_dir = Path(install_dir)

    def report(message: str) -> None:
        actions.append(message)
        if progress is not None:
            progress(message)

    stop_running_app()

    report("正在删除快捷方式…")
    delete_shortcut(start_menu_dir() / APP_NAME / f"{APP_NAME}.lnk")
    delete_shortcut(desktop_dir() / f"{APP_NAME}.lnk")
    delete_shortcut(startup_dir() / f"{APP_NAME}.lnk")
    try:
        menu_folder = start_menu_dir() / APP_NAME
        if menu_folder.is_dir():
            shutil.rmtree(menu_folder, ignore_errors=True)
    except OSError:
        pass

    report("正在移除注册表项…")
    unregister_uninstall()

    if remove_settings:
        report("正在删除设置文件…")
        try:
            shutil.rmtree(config_dir(), ignore_errors=True)
        except OSError:
            pass

    report("正在删除程序文件…")
    _remove_tree_later(install_dir)

    return actions


def _remove_tree_later(folder: Path) -> None:
    """Deletes a folder once the uninstaller has closed itself.

    The uninstaller runs from inside the folder it removes, so the files
    cannot go away right away. A small helper waits for this process to end
    and then does the work.
    """
    if not folder.exists():
        return

    # The helper lives in the temporary folder, not in the folder it
    # deletes, because a running script cannot remove its own folder.
    helper_dir = Path(tempfile.gettempdir()) / "batterytray-uninstall"
    helper_dir.mkdir(parents=True, exist_ok=True)
    bat = helper_dir / "cleanup.bat"
    try:
        bat.write_text(
            "@echo off\r\n"
            "ping 127.0.0.1 -n 3 > nul\r\n"
            f'rmdir /s /q "{folder}"\r\n'
            "del \"%~f0\"\r\n"
            "rmdir \"%~dp0\" 2>nul\r\n",
            encoding="mbcs", errors="replace")
    except OSError:
        # Without the helper the files stay behind, but the app is gone from
        # the start menu all the same.
        return

    try:
        # The working directory must not be the folder that gets deleted.
        subprocess.Popen(["cmd.exe", "/c", str(bat)], cwd=str(helper_dir))
    except (OSError, subprocess.SubprocessError):
        pass
