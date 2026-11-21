"""Runs the whole update the way the app does it.

The release is fetched from GitHub, the file is downloaded, the helper
is started and the app closes itself. A second program checks that the
new file really took the place of the old one.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from batterytray import update  # noqa: E402

WORK = ROOT / "out_test" / "_e2e"


def child(work: Path) -> int:
    """The app side: download, start the helper, then close."""
    target = work / "BatteryTray.exe"
    staged = work / "BatteryTray.exe.new"

    release = update.fetch_latest(timeout=30)
    print(f"   发布版本 {release.version}", flush=True)

    update.download_file(release.update_url, staged, timeout=180)
    size = staged.stat().st_size
    print(f"   下载完成 {size:,} 字节", flush=True)
    with staged.open("rb") as handle:
        print(f"   文件开头 {handle.read(2)!r}", flush=True)

    update.apply_update(staged, target)
    print("   交换助手已启动", flush=True)

    # The app closes itself now, so that the helper can do its work.
    time.sleep(0.5)
    return 0


def main() -> int:
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    target = WORK / "BatteryTray.exe"
    target.write_bytes(b"OLD-PROGRAM")

    proc = subprocess.Popen([sys.executable, __file__, "--child"])
    proc.wait(timeout=300)
    print("   程序已退出", flush=True)

    # The helper waits for the program and then swaps.
    for _ in range(60):
        time.sleep(0.5)
        if target.read_bytes()[:11] != b"OLD-PROGRAM":
            break

    print()
    print("=== 结果 ===")
    data = target.read_bytes()
    print(f"  目标文件大小 : {len(data):,} 字节")
    print(f"  开头         : {data[:2]!r} (MZ = 有效程序)")
    print(f"  是新版本吗   : {data[:2] == b'MZ'}")
    print(f"  .new 还在    : {(WORK / 'BatteryTray.exe.new').exists()}")
    return 0 if data[:2] == b"MZ" else 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        sys.exit(child(WORK))
    sys.exit(main())
