"""Checks that the buttons of the footer stay visible.

The footer used to be pushed out of the window as soon as the window
became smaller than the list of devices. This script resizes the window
and reports where the buttons ended up.
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
from batterytray.widgets import GlassButton  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "out_test"


class FakeApp:
    """Stands in for the tray app."""

    config = None

    def request_refresh(self):
        """The window does not need the real thing."""

    def rename_device(self, original, new):
        """The window does not need the real thing."""


def settle(window, rounds=30):
    """Lets Tk finish the layout."""
    for _ in range(rounds):
        window.update_idletasks()
        window.update()
        time.sleep(0.005)


def buttons_of(window):
    """Every GlassButton of the window."""
    found = []

    def walk(widget):
        for child in widget.winfo_children():
            if isinstance(child, GlassButton):
                found.append(child)
            walk(child)

    walk(window)
    return found


def main() -> None:
    """Prints where the buttons are at every size."""
    from PIL import ImageGrab

    OUT.mkdir(exist_ok=True)
    window = BatteryWindow(FakeApp())
    window.geometry("900x700")
    settle(window)
    window.set_devices([
        Device("Razer Viper V3 Pro Wireless", 87, kind="mouse"),
        Device("Keychron K3 Pro", 42, kind="keyboard"),
    ])
    settle(window)

    failures = 0
    for width, height in [(900, 700), (700, 500), (600, 400),
                          (540, 390), (540, 300)]:
        window.geometry(f"{width}x{height}")
        settle(window)

        top = window.winfo_rooty()
        bottom = top + window.winfo_height()
        real_w = window.winfo_width()
        real_h = window.winfo_height()

        print(f"=== asked {width}x{height}, got {real_w}x{real_h}")
        for button in buttons_of(window):
            y = button.winfo_rooty()
            inside = top <= y < bottom
            if not inside:
                failures += 1
            print(f"    BUTTON {button._text!r:12s} top={y - top:4d} "
                  f"inside={inside} viewable={button.winfo_viewable()}")

        x = window.winfo_rootx()
        image = ImageGrab.grab(bbox=(x, top, x + real_w, top + real_h))
        image.save(OUT / f"footer_{width}x{height}.png")

    window.destroy()
    print("FAILURES:", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
