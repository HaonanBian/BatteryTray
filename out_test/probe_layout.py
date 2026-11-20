"""Renders the main window at several sizes and saves a screenshot of each.

The point is to see where the header and the footer end up when the
window becomes small, and whether the buttons in the footer are still
visible.
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

OUT = Path(__file__).resolve().parent.parent / "out_test"


class FakeApp:
    """Stands in for the tray app."""

    config = None

    def request_refresh(self):
        """The window does not need the real thing."""

    def rename_device(self, original, new):
        """The window does not need the real thing."""


def main() -> None:
    """Saves one screenshot per window size."""
    from PIL import ImageGrab

    OUT.mkdir(exist_ok=True)
    window = BatteryWindow(FakeApp())
    window.geometry("440x300")
    window.update()
    window.set_devices([
        Device("Razer Viper V3 Pro Wireless", 87, kind="mouse"),
        Device("Keychron K3 Pro", 42, kind="keyboard"),
    ])
    for _ in range(30):
        window.update()
        time.sleep(0.02)

    for width, height in [(440, 300), (360, 260), (360, 200),
                          (300, 180), (440, 150), (280, 140)]:
        window.geometry(f"{width}x{height}")
        for _ in range(20):
            window.update()
            time.sleep(0.02)

        x, y = window.winfo_rootx(), window.winfo_rooty()
        w, h = window.winfo_width(), window.winfo_height()
        image = ImageGrab.grab(bbox=(x, y, x + w, y + h))
        name = OUT / f"layout_{width}x{height}.png"
        image.save(name)
        print("saved", name, image.size)

        # Report the geometry of the important parts.
        footer_buttons = []
        for child in window.winfo_children():
            if isinstance(child, type(window)) and child is window:
                continue
            for sub in child.winfo_children():
                for button in sub.winfo_children():
                    if type(button).__name__ == "GlassButton":
                        footer_buttons.append(button)

        for button in footer_buttons:
            print(f"   button {button._text!r} "
                  f"y={button.winfo_rooty() - y} "
                  f"h={button.winfo_height()} "
                  f"visible={button.winfo_viewable()}")

    window.destroy()


if __name__ == "__main__":
    main()
