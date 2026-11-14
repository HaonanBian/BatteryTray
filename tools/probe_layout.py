"""Renders the window and prints where the battery of the first card is."""

from __future__ import annotations

import sys
import time
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
    """Prints where the battery of the first card is."""
    from PIL import ImageGrab

    window = BatteryWindow(FakeApp())
    window.geometry("900x700")
    window.update()
    window.set_devices([
        Device("Razer Viper V3 Pro Wireless", 87, kind="mouse"),
    ])
    for _ in range(40):
        window.update()
        time.sleep(0.02)

    card = window._cards[0]
    print("card root", card.winfo_rootx(), card.winfo_rooty())
    for item in card.find_all():
        if card.type(item) == "image":
            print("image", card.coords(item), card.bbox(item))

    x, y = window.winfo_rootx(), window.winfo_rooty()
    width = window.winfo_width()
    height = window.winfo_height()
    image = ImageGrab.grab(bbox=(x - 6, y - 6, x + width + 6, y + height + 6))
    image.save(Path(__file__).resolve().parent.parent / "_probe.png")
    print("saved", image.size)

    window.destroy()


if __name__ == "__main__":
    main()
