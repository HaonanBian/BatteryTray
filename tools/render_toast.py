"""Renders the low battery card and saves a picture of it.

Only meant for looking at the card while it is being worked on:

    python tools/render_toast.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batterytray.dpi import set_dpi_aware  # noqa: E402

set_dpi_aware()
from batterytray.toast import LowBatteryToast  # noqa: E402
from batterytray.window import BatteryWindow  # noqa: E402

from capture import grab  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class FakeApp:
    """Stands in for the tray app."""

    config = None

    def request_refresh(self):
        """The window does not need the real thing."""

    def rename_device(self, original, new):
        """The window does not need the real thing."""


def main() -> None:
    """Draws the card for a device that is nearly empty."""
    window = BatteryWindow(FakeApp())
    window.withdraw()
    window.update()

    toast = LowBatteryToast(window)
    toast.show("Razer Viper V3 Pro Wireless", 9)
    for _ in range(40):
        window.update()
        time.sleep(0.02)

    # The card fades in; the picture wants it at full strength, and it
    # must not close itself while the picture is taken.
    toast._cancel_life()
    toast.attributes("-alpha", 1.0)
    toast.update()

    image = grab(toast, own_handle=True)
    out = ROOT / "_toast_new.png"
    image.save(out)
    print("saved", out, image.size)

    toast._destroy()
    window.destroy()


if __name__ == "__main__":
    main()
