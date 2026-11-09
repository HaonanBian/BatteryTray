"""Start-with-Windows registration.

Uses a shortcut in the Startup folder rather than an ``HKCU\\...\\Run`` entry.
Unsigned binaries in a Run key are skipped by some Windows 11 builds, which
both ``damianyoko/viper-tray`` and ``nuxencs/razertray`` report.

The shortcut is written through PowerShell's ``WScript.Shell`` COM object.
That avoids depending on pywin32, which keeps the packaged executable small
and avoids the dynamic-dispatch property-set quirks of late-bound COM.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .config import APP_DIR_NAME

# The name of the shortcut file.
SHORTCUT_NAME = f"{APP_DIR_NAME}.lnk"


def _startup_dir() -> Path:
    """Returns the per-user Startup folder."""
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "Microsoft" / "Start Menu" / "Programs" / "Startup"


def _shortcut_path() -> Path:
    """The full path of the startup shortcut."""
    return _startup_dir() / SHORTCUT_NAME


def _target_and_arguments() -> tuple[str, str]:
    """The program to start and the arguments to pass to it.

    The target must not be quoted: ``WScript.Shell`` stores the target as a
    plain path, and a quoted one ends up empty when Windows reads it back.
    The arguments carry the quotes instead.
    """
    if getattr(sys, "frozen", False):
        return sys.executable, ""

    # Running from source: start the entry script with the current
    # interpreter.
    script = Path(sys.argv[0]).resolve()
    if script.name == "-" or not script.is_file():
        # The program was piped in through stdin, so there is no script to
        # point at. Falling back to the package entry point keeps the
        # shortcut working.
        script = Path(__file__).resolve().parent.parent / "main.py"
    return sys.executable, f'"{script}"'


def _create_shortcut(path: Path) -> bool:
    """Writes the .lnk file through PowerShell's WScript.Shell."""
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)

    target, arguments = _target_and_arguments()
    working_dir = str(path.parent)

    # Single quotes in the values would break out of the PowerShell string.
    for value in (str(path), target, working_dir):
        if "'" in value:
            return False

    script = (
        f"$s = (New-Object -ComObject WScript.Shell)"
        f".CreateShortcut('{path}');"
        f"$s.TargetPath = '{target}';"
    )
    if arguments:
        script += f"$s.Arguments = '{arguments}';"
    script += (
        f"$s.WorkingDirectory = '{working_dir}';"
        f"$s.Description = 'BatteryTray - mouse and headset battery levels';"
        f"$s.Save()"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=20,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return result.returncode == 0 and path.exists()


def is_enabled() -> bool:
    """Whether the app is set to start with Windows."""
    return _shortcut_path().exists()


def enable() -> bool:
    """Registers the app to start with Windows."""
    return _create_shortcut(_shortcut_path())


def disable() -> bool:
    """Removes the startup registration."""
    path = _shortcut_path()
    try:
        if path.exists():
            path.unlink()
    except OSError:
        return False
    return True


def set_enabled(enabled: bool) -> bool:
    """Turns the startup registration on or off."""
    return enable() if enabled else disable()


def startup_folder() -> Path:
    """The Startup folder, so the user can open it and see the shortcut."""
    return _startup_dir()


def describe() -> str:
    """A short description of the current registration."""
    path = _shortcut_path()
    if not path.exists():
        return "未注册"
    target, arguments = _target_and_arguments()
    return f"{target} {arguments}".strip()
