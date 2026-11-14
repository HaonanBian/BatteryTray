"""Renders the tray panel and saves a picture of it.

Only meant for looking at the panel while it is being worked on:

    python tools/render_panel.py
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
        """The panel does not need the real thing."""

    def rename_device(self, original, new):
        """The panel does not need the real thing."""


def main() -> None:
    """Draws the panel with a few devices in it."""
    window = BatteryWindow(FakeApp())
    window.withdraw()

    panel = window.quick_panel
    panel.set_devices([
        Device("Razer Viper V3 Pro Wireless", 86, kind="mouse",
               connection="2.4GHz 无线"),
        Device("Keyboard", 62, kind="keyboard"),
        Device("WH-CH720N Hands-Free AG", 74, kind="headset",
               connection="蓝牙连接"),
    ])

    window.update()
    window.update_idletasks()
    panel.geometry("+700+200")
    panel.deiconify()
    panel.lift()
    panel._round_corners()
    for _ in range(40):
        window.update()
        time.sleep(0.03)

    image = grab(panel)
    out = Path(__file__).resolve().parent.parent / "_panel_new.png"
    image.save(out)
    print("saved", out, image.size)

    panel.destroy()
    window.destroy()


if __name__ == "__main__":
    main()
