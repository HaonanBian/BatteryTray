"""Tests that the app really starts again after an update.

The update waits for the running copy to go away, swaps the file and
starts the new one. This script does the same three steps in a scratch
folder and looks at what happens, so a broken update is caught before it
is published.

The file that stands in for the app has to be a program Windows can
really start: a text file that only carries the name of one is refused
by the system ("this app can't run on your PC"), and the test would
report a failure that is not there. The built program is used when it is
around, otherwise a copy of the command interpreter.

    python tools/test_update_restart.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batterytray import update  # noqa: E402

BUILT = Path(__file__).resolve().parent.parent / "dist" / "BatteryTray.exe"


def say(text: str) -> None:
    """Prints a line, even when the console cannot show every character."""
    line = text + "\n"
    try:
        sys.stdout.write(line)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        sys.stdout.write(line.encode(encoding, "replace").decode(encoding))
    sys.stdout.flush()


def processes(folder: Path) -> list[tuple[int, int]]:
    """The (pid, parent pid) of the copies that run from the folder."""
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name='BatteryTray.exe'\" | "
        "ForEach-Object { \"$($_.ProcessId)|$($_.ParentProcessId)|"
        "$($_.ExecutablePath)\" }")
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", script],
                            capture_output=True, text=True)
    found = []
    for line in result.stdout.splitlines():
        parts = line.strip().split("|")
        if len(parts) != 3:
            continue
        pid, parent, exe = parts
        if str(Path(exe).parent).lower() != str(folder).lower():
            continue
        try:
            found.append((int(pid), int(parent)))
        except ValueError:
            pass
    return found


def stop_copies(folder: Path) -> None:
    """Closes every copy that runs from the folder."""
    for pid, _ in processes(folder):
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       capture_output=True)


def stand_in() -> tuple[bytes, str]:
    """The bytes of a program that can be started, and where it came from."""
    if BUILT.is_file():
        return BUILT.read_bytes(), "构建好的 BatteryTray.exe"
    system = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    shell = system / "System32" / "cmd.exe"
    return shell.read_bytes(), "cmd.exe 的副本"


def real_pid(folder: Path, started: int) -> int:
    """The pid of the program itself.

    A one-file build of PyInstaller runs the program in a child process
    and waits for it in the process that was started. The app knows
    itself under the pid of that child, and that is the pid the update
    waits for.
    """
    for pid, parent in processes(folder):
        if parent == started:
            return pid
    return started


def main() -> int:
    other = subprocess.run(
        ["tasklist", "/nh", "/fi", "IMAGENAME eq BatteryTray.exe"],
        capture_output=True, text=True)
    if "BatteryTray.exe" in other.stdout:
        say("先退出正在运行的 BatteryTray，再跑这个测试。")
        return 1

    program, where = stand_in()
    say(f"用来代替程序的文件: {where} ({len(program)} 字节)")

    folder = Path(tempfile.mkdtemp(prefix="batterytray-restart-"))
    target = folder / "BatteryTray.exe"
    target.write_bytes(program)
    source = folder / "BatteryTray.exe.new"
    source.write_bytes(program)

    try:
        # The copy that is running when the update starts.
        child = subprocess.Popen([str(target)], cwd=str(folder))
        time.sleep(3.0)
        if not processes(folder):
            say("旧版本没有启动起来 [FAIL]")
            return 1
        pid = real_pid(folder, child.pid)
        say(f"旧版本已启动, pid = {pid}")

        # What the app does when it updates itself: the swap runs as soon
        # as the running copy is gone.
        known = {item[0] for item in processes(folder)}
        script = update._replace_script(
            target, source, folder / "BatteryTray.exe.old", pid)
        subprocess.Popen(["cmd.exe", "/c", str(script)],
                         cwd=str(script.parent),
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

        # The file must not be touched while the app still runs.
        time.sleep(3.0)
        if not source.exists():
            say("旧进程还在时就换了文件 [FAIL]")
            return 1
        say("旧进程还在时没有换文件 [OK]")

        # The app closes itself once the update is handed over.
        say("关闭旧版本…")
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        time.sleep(1.0)

        for _ in range(60):
            time.sleep(0.5)
            if not source.exists():
                say("文件已替换 [OK]")
                break
        else:
            say("文件没有替换 [FAIL]")
            return 1

        # The helper starts the new copy. The copies that were there
        # before do not count.
        for _ in range(40):
            time.sleep(0.5)
            fresh = [item for item in processes(folder) if item[0] not in known]
            if fresh:
                say("新版本已自动启动 [OK]")
                return 0

        say("新版本没有自动启动 [FAIL]")
        return 1
    finally:
        stop_copies(folder)
        for item in folder.iterdir():
            try:
                item.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
