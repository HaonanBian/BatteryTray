"""Prints the items of the device cards in the main window.

    python tools/inspect_cards.py
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
    """Prints what is drawn on the first card."""
    window = BatteryWindow(FakeApp())
    window.geometry("900x700")
    window.update()
    window.set_devices([
        Device("Razer Viper V3 Pro Wireless", 87, kind="mouse",
               product_id=0xC1, connection="2.4GHz 无线",
               polling_rate=8000, dpi=1600),
    ])
    window.update_idletasks()
    window.update()

    card = window._cards[0]
    print("card:", card.winfo_width(), "x", card.winfo_height())
    print("name label:", card.name_label.cget("text"),
          "at", card.name_label.winfo_x(), card.name_label.winfo_y())
    print("status label:", repr(card.status_label.cget("text")),
          "at", card.status_label.winfo_x(), card.status_label.winfo_y())
    print("detail rows:", card._detail_rows)
    print("--- canvas items ---")
    for item in card.find_all():
        kind = card.type(item)
        box = card.bbox(item)
        if kind == "text":
            print("text", repr(card.itemcget(item, "text")),
                  "at", box, "fill", card.itemcget(item, "fill"),
                  "tags", card.gettags(item))
        elif kind == "window":
            print("window", box, "tags", card.gettags(item))
        else:
            print(kind, box, "tags", card.gettags(item))

    window.destroy()


if __name__ == "__main__":
    main()
