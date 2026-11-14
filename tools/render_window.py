"""Renders the main window and saves a picture of it.

Only meant for looking at the window while it is being worked on:

    python tools/render_window.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batterytray.app import Device  # noqa: E402
from batterytray.dpi import set_dpi_aware  # noqa: E402

set_dpi_aware()
from batterytray.window import BatteryWindow  # noqa: E402

from capture import grab  # noqa: E402


class FakeApp:
    """Stands in for the tray app."""

    config = None

    def request_refresh(self):
        """The window does not need the real thing."""

    def rename_device(self, original, new):
        """The window does not need the real thing."""


def main() -> None:
    """Draws the window with a few devices in it."""
    window = BatteryWindow(FakeApp())
    window.geometry("900x700")
    window.update()
    window.set_devices([
        Device("Razer Viper V3 Pro Wireless", 87, kind="mouse",
               product_id=0xC1, connection="2.4GHz 无线",
               polling_rate=8000, dpi=1600),
        Device("WH-CH720N Hands-Free AG", 24, kind="headset"),
        Device("ROG Keris Wireless Aimpoint", 100, kind="mouse",
               product_id=0x00C1, connection="有线连接",
               polling_rate=1000, dpi=800, charging=True),
        Device("Xbox Wireless Controller", None, kind="controller",
               connected=False),
    ])
    for _ in range(60):
        window.update()
        time.sleep(0.02)

    image = grab(window)
    out = Path(__file__).resolve().parent.parent / "_window_new.png"
    image.save(out)
    print("saved", out, image.size)

    window.destroy()


if __name__ == "__main__":
    main()
