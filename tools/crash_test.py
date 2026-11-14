"""Tries to make the window crash on purpose.

    python tools/crash_test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batterytray.app import Device  # noqa: E402
from batterytray.dpi import set_dpi_aware  # noqa: E402

set_dpi_aware()

from batterytray.window import BatteryWindow  # noqa: E402


class FakeApp:
    """Stands in for the tray app."""

    config = None

    def request_refresh(self):
        """The window does not need the real thing."""

    def rename_device(self, original, new):
        """The window does not need the real thing."""


def main() -> None:
    """Resizes the window while devices are shown."""
    window = BatteryWindow(FakeApp())
    devices = [Device("Mouse", 80, kind="mouse"),
               Device("Headset", 90, kind="headset")]

    window.geometry("550x600")
    window.update_idletasks()
    window.set_devices(devices)
    window.update_idletasks()
    print("columns:", window._columns)

    for width in (1000, 550, 1400, 700, 1900, 800):
        print("resizing to", width)
        window.geometry(f"{width}x600")
        window.update_idletasks()
        window.update()
        print("  columns:", window._columns)

    print("done")
    window.destroy()


if __name__ == "__main__":
    main()
