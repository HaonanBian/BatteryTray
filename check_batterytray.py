"""Checks what BatteryTray can see on this machine.

The script prints the answer of every driver, so that a machine where
nothing is shown can be examined. Run it with the same account that
starts BatteryTray.

    python check_batterytray.py
"""

from __future__ import annotations

import sys

try:
    from batterytray.diagnostics import build_report
except ImportError:
    print("找不到 batterytray 模块，请在这个项目的文件夹里运行本脚本。")
    raise SystemExit(1)


def main() -> int:
    print(build_report())
    return 0


if __name__ == "__main__":
    sys.exit(main())
