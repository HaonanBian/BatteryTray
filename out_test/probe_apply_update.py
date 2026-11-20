"""Proves that the update really replaces the file and starts it again.

A copy of the interpreter stands in for the app. The update has to wait
for the running copy, swap the file and start the new one.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batterytray import update  # noqa: E402

WORK = Path(tempfile.gettempdir()) / "batterytray-update-test"
# The name carries the time, so a copy that is still running from an
# earlier run does not get in the way.
PROGRAM = f"batterytray-fake-{int(time.time())}.exe"


def running() -> bool:
    """Whether the fake program is running."""
    result = subprocess.run(["tasklist", "/nh", "/fo", "csv"],
                            capture_output=True, text=True)
    return PROGRAM.lower() in result.stdout.lower()


def fake_program() -> Path | None:
    """A program that can be copied around and that stays alive.

    The interpreter of the system is used, because a copy of it can be
    started from anywhere and keeps running until it is closed.
    """
    candidates = [
        Path(r"C:\Users\asus\AppData\Local\Programs\Python\Python313"
             r"\python.exe"),
        Path(sys.executable),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return shutil.which("python.exe")


def main() -> None:
    """Runs the swap and checks that the new copy was started."""
    if WORK.exists():
        for item in WORK.iterdir():
            try:
                item.unlink()
            except OSError:
                # A copy that is still running keeps its file open.
                pass
    WORK.mkdir(parents=True, exist_ok=True)

    interpreter = fake_program()
    if interpreter is None:
        print("SKIP: no interpreter to copy")
        return 0

    old = WORK / PROGRAM
    old.write_bytes(interpreter.read_bytes())
    new = WORK / f"{PROGRAM}.new"
    # The new file gets a mark at the end, so the two can be told apart.
    new.write_bytes(interpreter.read_bytes() + b"\nMARK\n")

    # A child process stands in for the running app.
    child = subprocess.Popen(["cmd.exe", "/c", "ping 127.0.0.1 -n 12 > nul"])
    time.sleep(0.5)

    script = update._replace_script(old, new, WORK / f"{PROGRAM}.old",
                                    child.pid)
    print("script:", script)
    subprocess.Popen(["cmd.exe", "/c", str(script)], cwd=str(script.parent))

    # The swap must not happen while the app is still running. The new
    # file is still lying next to the old one at that point.
    time.sleep(4)
    early_ok = old.read_bytes() != new.read_bytes()
    print("after 4s the file was not swapped:", early_ok)

    # Now the app goes away.
    child.wait(timeout=30)
    print("the app process is gone")

    # The script waits a moment and then does the swap. The new file is
    # moved into the place of the old one, so it is gone afterwards.
    deadline = time.time() + 30
    while time.time() < deadline:
        if old.exists() and not new.exists():
            break
        time.sleep(0.3)

    swapped = old.exists() and not new.exists()
    print("the file was swapped:", swapped)

    # The new copy has to be started.
    started = False
    deadline = time.time() + 20
    while time.time() < deadline:
        if running():
            started = True
            break
        time.sleep(0.5)
    print("the new copy was started:", started)

    ok = early_ok and swapped and started
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
