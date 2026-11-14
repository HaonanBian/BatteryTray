"""Prints what is drawn on the card, to check the battery.

    python tools/probe_card.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batterytray.app import Device  # noqa: E402
from batterytray.dpi import set_dpi_aware  # noqa: E402

set_dpi_aware()

import tkinter as tk  # noqa: E402

from batterytray.window import DeviceCard  # noqa: E402


def main() -> None:
    """Prints the items of the card."""
    root = tk.Tk()
    root.geometry("620x300+30+30")

    card = DeviceCard(root, "Microsoft YaHei UI", 96.0)
    card.pack(fill="x", padx=10, pady=6)
    card.update(device=Device("Razer Viper V3 Pro Wireless", 87, kind="mouse"))
    root.update()

    print("card size:", card.winfo_width(), card.winfo_height())
    print("battery:", card._battery_width(), card._battery_height(),
          card._battery_top())
    for item in card.find_all():
        kind = card.type(item)
        if kind == "polygon":
            print(item, kind, card.coords(item)[:4], card.itemcget(item, "fill"),
                  "outline", card.itemcget(item, "outline"))
        elif kind == "text":
            print(item, kind, card.coords(item), repr(card.itemcget(item, "text")))
        elif kind == "rectangle":
            print(item, kind, card.coords(item), card.itemcget(item, "fill"))
        else:
            print(item, kind, card.coords(item))

    root.destroy()


if __name__ == "__main__":
    main()
