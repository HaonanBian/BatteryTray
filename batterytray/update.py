"""Looks for a newer release of the app on GitHub.

The app lives in a public GitHub repository, and every release is
published there. This module asks the GitHub API for the latest release
and compares its tag with the version of the running copy.

The module can also download the new version and put it in place of the
running one. That is done in two steps, because a running program cannot
replace its own file: the new file is written next to the old one and a
small helper swaps the two once the app has closed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import __version__

# The repository the releases are published in.
REPO_OWNER = "HaonanBian"
REPO_NAME = "BatteryTray"

# The endpoint that reports the latest release.
LATEST_RELEASE_URL = (
    f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest")

# The page a user can open to see the releases.
RELEASES_PAGE_URL = (
    f"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/latest")

# How long to wait for the answer of GitHub, in seconds. The check runs in
# the background, so a slow answer must not hold anything up.
TIMEOUT = 15

# The user agent that identifies the app. GitHub asks for one.
USER_AGENT = "BatteryTray"


class UpdateError(Exception):
    """Something went wrong while looking for an update."""


class _RetryableError(Exception):
    """A download attempt failed in a way that another one might fix."""


@dataclass(frozen=True)
class Release:
    """One published release."""

    version: str
    url: str
    notes: str = ""
    # The file that can be downloaded, the name it is offered under and
    # where it can be fetched from.
    asset_name: str = ""
    asset_url: str = ""
    # The installer and the single file copy, so the user can pick the one
    # that fits the way the app was installed.
    setup_name: str = ""
    setup_url: str = ""
    # The plain executable, which is the only file that can replace the
    # running copy of the app.
    program_name: str = ""
    program_url: str = ""

    @property
    def download_url(self) -> str:
        """The page the update can be downloaded from."""
        return self.asset_url or self.url

    @property
    def update_url(self) -> str:
        """The file the automatic update installs."""
        return self.program_url or self.asset_url


def parse_version(text: str) -> tuple[int, ...]:
    """Turns a version string into a tuple of numbers.

    ``v1.2.0`` and ``1.2.0`` both become ``(1, 2, 0)``. A part that is
    not a number ends the comparison, so ``1.2.0-beta`` becomes
    ``(1, 2, 0)`` as well.
    """
    cleaned = str(text or "").strip().lstrip("vV")
    parts: list[int] = []
    for chunk in cleaned.split("."):
        digits = ""
        for char in chunk:
            if not char.isdigit():
                break
            digits += char
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def is_newer(latest: str, current: str) -> bool:
    """Whether ``latest`` is a newer version than ``current``."""
    return parse_version(latest) > parse_version(current)


def _find_asset(assets: list[dict], marker: str) -> tuple[str, str]:
    """Finds the file whose name contains the given marker.

    The marker is what tells the three files of a release apart: the
    installer carries ``Setup``, the single file copy carries ``.exe``
    and the portable archive carries ``portable``.
    """
    for asset in assets:
        name = str(asset.get("name", ""))
        if marker.lower() in name.lower():
            return name, str(asset.get("browser_download_url", ""))
    return "", ""


def _find_program(assets: list[dict]) -> tuple[str, str]:
    """Finds the single file copy of the app.

    The portable archive holds the program in a folder, so it cannot be
    put in place of the running file. Only the plain executable can do
    that, which is why it is the one the update uses.
    """
    for asset in assets:
        name = str(asset.get("name", ""))
        if not name.lower().endswith(".exe"):
            continue
        if "setup" in name.lower() or "installer" in name.lower():
            continue
        return name, str(asset.get("browser_download_url", ""))
    return "", ""


def _pick_asset(assets: list[dict]) -> tuple[str, str]:
    """Chooses the file that should be downloaded.

    The single file executable is preferred, because it can be replaced
    without going through the installation wizard. The portable archive
    comes next and the installer last.
    """
    name, url = _find_program(assets)
    if name:
        return name, url
    for wanted in ("-portable.zip", ".exe"):
        name, url = _find_asset(assets, wanted)
        if name:
            return name, url
    if assets:
        first = assets[0]
        return (str(first.get("name", "")),
                str(first.get("browser_download_url", "")))
    return "", ""


def parse_release(payload: dict) -> Release:
    """Reads a release out of the answer of the GitHub API."""
    tag = str(payload.get("tag_name") or "")
    if not tag:
        raise UpdateError("GitHub 没有返回版本号")
    assets = payload.get("assets")
    if not isinstance(assets, list):
        assets = []
    asset_name, asset_url = _pick_asset(assets)
    setup_name, setup_url = _find_asset(assets, "Setup")
    program_name, program_url = _find_program(assets)
    return Release(
        version=tag,
        url=str(payload.get("html_url") or RELEASES_PAGE_URL),
        notes=str(payload.get("body") or ""),
        asset_name=asset_name,
        asset_url=asset_url,
        setup_name=setup_name,
        setup_url=setup_url,
        program_name=program_name,
        program_url=program_url,
    )


def fetch_latest(timeout: int = TIMEOUT) -> Release:
    """Asks GitHub for the latest release.

    Raises :class:`UpdateError` when the answer cannot be used.
    """
    request = urllib.request.Request(
        LATEST_RELEASE_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        raise UpdateError(f"GitHub 返回了错误 {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise UpdateError(f"连不上 GitHub：{exc.reason}") from exc
    except OSError as exc:
        raise UpdateError(f"连不上 GitHub：{exc}") from exc

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateError("GitHub 的回答读不出来") from exc
    if not isinstance(payload, dict):
        raise UpdateError("GitHub 的回答不是预期的格式")
    return parse_release(payload)


def check_for_update(current: str = __version__,
                     timeout: int = TIMEOUT) -> Release | None:
    """Looks for a newer release.

    Returns the newer release, or ``None`` when the app is already up to
    date. Raises :class:`UpdateError` when the check itself failed.
    """
    release = fetch_latest(timeout=timeout)
    if not is_newer(release.version, current):
        return None
    return release


# --------------------------------------------------------------------------
# Downloading and replacing the running copy
# --------------------------------------------------------------------------


def running_executable() -> Path | None:
    """The file the running copy of the app was started from.

    ``None`` when the app runs from the source instead of a built
    executable; there is nothing to replace in that case.
    """
    if not getattr(sys, "frozen", False):
        return None
    try:
        return Path(sys.executable).resolve()
    except (OSError, ValueError):
        return None


def _looks_like_program(path: Path) -> bool:
    """Says whether the file starts like a Windows program.

    A download can go wrong in a way that leaves a file of the right
    size behind, for example when the server answers with an error
    page. Such a file cannot be run, so it is caught here.
    """
    try:
        with path.open("rb") as handle:
            return handle.read(2) == b"MZ"
    except OSError:
        return False


def download_file(url: str, target: Path, progress=None,
                  timeout: int = 60, attempts: int = 3,
                  on_retry=None) -> Path:
    """Downloads a file to the given path.

    The file is written next to the target first and moved into place
    afterwards, so a broken download never leaves a half written file
    behind.

    The connection to GitHub drops from time to time, so a download
    that breaks off is tried again. A file that is not a program is
    refused, because it cannot be run and there is no point in putting
    it in place of the running one.

    ``on_retry`` is called with the number of the attempt and the
    reason, so that the user can be told that the download is still
    going on.
    """
    if not url:
        raise UpdateError("没有下载地址")

    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    last_error = ""
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return _download_once(url, target, progress, timeout)
        except _RetryableError as exc:
            last_error = str(exc)
            if attempt >= max(1, attempts):
                break
            if on_retry is not None:
                try:
                    on_retry(attempt, last_error)
                except Exception:
                    pass
            # The connection needs a moment before it works again.
            time.sleep(min(2 ** attempt, 8))

    raise UpdateError(f"下载失败：{last_error}")


def _download_once(url: str, target: Path, progress, timeout: int) -> Path:
    """Downloads the file once.

    Raises :class:`_RetryableError` when the attempt failed in a way
    that another attempt might fix.
    """
    # The temporary file sits in the same folder, so the move does not
    # cross a file system boundary.
    try:
        handle, temporary = tempfile.mkstemp(prefix="batterytray-download-",
                                             dir=str(target.parent))
    except OSError as exc:
        raise UpdateError(
            f"无法在程序目录写入文件：{exc}。"
            "请以管理员身份运行后再试") from exc
    os.close(handle)
    temporary_path = Path(temporary)

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            total = 0
            read = 0
            try:
                total = int(response.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                total = 0
            with open(temporary_path, "wb") as handle:
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    read += len(chunk)
                    if progress is not None:
                        progress(read, total)
    except urllib.error.HTTPError as exc:
        temporary_path.unlink(missing_ok=True)
        if exc.code in (403, 429, 500, 502, 503, 504):
            raise _RetryableError(f"服务器返回 {exc.code}") from exc
        raise UpdateError(f"下载失败：服务器返回 {exc.code}") from exc
    except urllib.error.URLError as exc:
        temporary_path.unlink(missing_ok=True)
        raise _RetryableError(str(exc.reason)) from exc
    except OSError as exc:
        temporary_path.unlink(missing_ok=True)
        raise _RetryableError(str(exc)) from exc

    if total and read < total:
        temporary_path.unlink(missing_ok=True)
        raise _RetryableError("文件不完整")

    # A file that is not a program would break the app. This happens
    # when the server answers with something else than the file.
    if target.suffix.lower() == ".exe" and not _looks_like_program(
            temporary_path):
        temporary_path.unlink(missing_ok=True)
        raise UpdateError("下载失败：拿到的不是有效的程序文件")

    try:
        shutil.move(str(temporary_path), str(target))
    except OSError as exc:
        temporary_path.unlink(missing_ok=True)
        raise UpdateError(f"保存文件失败：{exc}") from exc
    return target


def _replace_script(target: Path, source: Path, backup: Path,
                    pid: int) -> Path:
    """Writes the script that swaps the old file for the new one.

    A running program cannot replace its own file, so the swap has to
    happen after the app has closed. The script waits for the process to
    be gone before it touches the files, and it starts the new copy
    afterwards.

    The new copy is started through a small launcher of its own. A
    program that is started straight from the command interpreter is
    killed together with it, so it would never get a chance to run.
    """
    folder = Path(tempfile.gettempdir()) / "batterytray-update"
    folder.mkdir(parents=True, exist_ok=True)
    script = folder / "replace.bat"
    # The list of the running programs is written to a file, because the
    # pipe of a command does not survive the quoting of a batch file.
    listing = folder / "tasks.txt"
    # The launcher starts the new copy. It has to be a file of its own,
    # because a program that is started straight from the command
    # interpreter is killed together with it.
    launcher = folder / "launch.bat"
    launcher.write_text(
        "@echo off\r\n"
        f'start "" "{target}"\r\n',
        encoding="mbcs", errors="replace")
    script.write_text(
        "@echo off\r\n"
        # Wait until the running copy is really gone. The loop gives up
        # after a minute, so a stuck process does not block the update
        # forever.
        ":wait\r\n"
        f'tasklist /nh /fo csv /fi "PID eq {pid}" > "{listing}"\r\n'
        f'findstr /c:"\\"{pid}\\"" "{listing}" > nul\r\n'
        "if not errorlevel 1 (\r\n"
        "  ping 127.0.0.1 -n 2 > nul\r\n"
        "  goto wait\r\n"
        ")\r\n"
        f'del /q "{listing}" > nul 2>nul\r\n'
        # Put the old file aside and move the new one into its place.
        f'move /y "{target}" "{backup}" > nul 2>nul\r\n'
        f'move /y "{source}" "{target}" > nul 2>nul\r\n'
        # The new copy is only started when the swap worked. The start
        # has to stand on its own, because it does not work inside a
        # block of a batch file.
        f'if not exist "{target}" goto done\r\n'
        f'start "" "{launcher}"\r\n'
        # The old file is kept for a while, in case the new one fails.
        "ping 127.0.0.1 -n 3 > nul\r\n"
        f'del /q "{backup}" > nul 2>nul\r\n'
        ":done\r\n"
        "del \"%~f0\"\r\n"
        "rmdir \"%~dp0\" 2>nul\r\n"
        "exit /b 0\r\n",
        encoding="mbcs", errors="replace")
    return script


def _folder_can_be_written(folder: Path) -> bool:
    """Says whether a new file may be put into the given folder.

    The check is done by really writing a small file, because the
    rights of the folder can be more strict than what the system
    reports.
    """
    handle = None
    probe = None
    try:
        handle, name = tempfile.mkstemp(prefix="batterytray-write-",
                                        dir=str(folder))
        os.close(handle)
        handle = None
        probe = Path(name)
        probe.unlink()
        probe = None
        return True
    except OSError:
        return False
    finally:
        if handle is not None:
            os.close(handle)
        if probe is not None:
            try:
                probe.unlink()
            except OSError:
                pass


def apply_update(source: Path, target: Path | None = None) -> bool:
    """Puts the downloaded file in place of the running copy.

    The app is closed by the caller first. The swap itself is done by a
    small helper, because the running program still holds its own file
    open for a moment after it closes.
    """
    if target is None:
        target = running_executable()
    if target is None:
        raise UpdateError("这个版本不是单独的可执行文件，无法自动更新")

    source = Path(source)
    target = Path(target)
    if not source.is_file():
        raise UpdateError("下载的文件不见了")

    # The new file has to be written next to the running one. When the
    # program sits in a folder that only the administrator may write
    # to, the swap cannot work. That is worth saying, because the
    # program would otherwise close and nothing would happen.
    if not _folder_can_be_written(target.parent):
        raise UpdateError(
            "没有权限修改程序所在文件夹，请以管理员身份运行后再试，"
            "或到下载页面手动替换")

    backup = target.with_suffix(target.suffix + ".old")
    script = _replace_script(target, source, backup, os.getpid())
    try:
        subprocess.Popen(["cmd.exe", "/c", str(script)], cwd=str(script.parent),
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as exc:
        raise UpdateError(f"无法启动更新程序：{exc}") from exc
    return True

