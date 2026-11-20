"""Tries the wait part of the update script on its own.

The part that waits for the running copy has to notice when the process
is gone. This script runs it with a process that really exists and one
that does not.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

WORK = Path(tempfile.gettempdir()) / "batterytray-wait-test"


def main() -> None:
    """Runs the wait loop with a living and with a dead process."""
    WORK.mkdir(parents=True, exist_ok=True)
    listing = WORK / "tasks.txt"

    # ---- A process that is really running ----
    child = subprocess.Popen(["cmd.exe", "/c", "ping 127.0.0.1 -n 20 > nul"])
    time.sleep(0.5)

    script = WORK / "wait.bat"
    script.write_text(
        "@echo off\r\n"
        ":wait\r\n"
        f'tasklist /nh /fo csv /fi "PID eq {child.pid}" > "{listing}"\r\n'
        f'findstr /c:"\\"{child.pid}\\"" "{listing}" > nul\r\n'
        "if not errorlevel 1 (\r\n"
        "  ping 127.0.0.1 -n 2 > nul\r\n"
        "  goto wait\r\n"
        ")\r\n"
        "echo GONE\r\n",
        encoding="mbcs")

    result = subprocess.run(["cmd.exe", "/c", str(script)],
                            capture_output=True, text=True, timeout=20)
    print("listing:", listing.read_text(encoding="mbcs", errors="replace")
          if listing.exists() else "(missing)")
    print("output:", result.stdout.strip())
    alive_ok = "GONE" not in result.stdout

    # ---- A process that does not exist ----
    script.write_text(
        "@echo off\r\n"
        ":wait\r\n"
        f'tasklist /nh /fo csv /fi "PID eq 999999" > "{listing}"\r\n'
        "findstr /c:\"\\\"999999\\\"\" \"%s\" > nul\r\n" % listing
        + "if not errorlevel 1 (\r\n"
        "  ping 127.0.0.1 -n 2 > nul\r\n"
        "  goto wait\r\n"
        ")\r\n"
        "echo GONE\r\n",
        encoding="mbcs")
    result = subprocess.run(["cmd.exe", "/c", str(script)],
                            capture_output=True, text=True, timeout=20)
    print("output2:", result.stdout.strip())
    dead_ok = "GONE" in result.stdout

    child.kill()
    child.wait(timeout=10)

    print("alive detected:", alive_ok, "| dead detected:", dead_ok)
    print("OK" if alive_ok and dead_ok else "FAIL")
    return 0 if alive_ok and dead_ok else 1


if __name__ == "__main__":
    sys.exit(main())
