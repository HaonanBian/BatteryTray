"""Renders a single card and saves a picture of it.

    python tools/render_card.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batterytray.app import Device  # noqa: E402
from batterytray.dpi import set_dpi_aware  # noqa: E402

set_dpi_aware()

import tkinter as tk  # noqa: E402

from batterytray.window import DeviceCard  # noqa: E402

CASES = [
    ("Razer Viper V3 Pro Wireless", 87, "mouse"),
    ("WH-CH720N Hands-Free AG", 24, "headset"),
    ("ROG Keris Wireless Aimpoint", 100, "mouse"),
    ("Xbox Wireless Controller", None, "controller"),
]


def main() -> None:
    """Paints the cards."""
    from PIL import ImageGrab

    root = tk.Tk()
    root.configure(bg="#0B0C10")
    root.geometry("620x800+30+30")
    root.attributes("-topmost", True)
    root.lift()
    root.focus_force()

    for name, percent, kind in CASES:
        card = DeviceCard(root, "Microsoft YaHei UI", 96.0)
        card.pack(fill="x", padx=10, pady=6)
        card.update(device=Device(name, percent, kind=kind))

    for _ in range(40):
        root.update()
        time.sleep(0.02)

    root.lift()
    root.update()
    time.sleep(0.3)
    root.update()

    x, y = root.winfo_rootx(), root.winfo_rooty()
    width = root.winfo_width()
    height = root.winfo_height()
    image = ImageGrab.grab(bbox=(x - 6, y - 6, x + width + 6, y + height + 6))
    out = Path(__file__).resolve().parent.parent / "_cards.png"
    image.save(out)
    print("saved", out, image.size)

    root.destroy()


if __name__ == "__main__":
    main()
