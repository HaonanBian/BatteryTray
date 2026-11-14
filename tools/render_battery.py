"""Draws the battery icon big, so the shape can be judged.

    python tools/render_battery.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batterytray.dpi import set_dpi_aware  # noqa: E402

set_dpi_aware()

import tkinter as tk  # noqa: E402

from batterytray.widgets import BG_CARD, draw_battery  # noqa: E402

# The size the battery is drawn in, and the size of the text in it.
SIZES = [
    ("card", 74, 28, 9),
    ("panel", 200, 46, 15),
    ("row", 48, 20, 8),
]
CASES = [(87, False), (24, False), (100, True), (None, False), (5, False)]
ZOOM = 4


def main() -> None:
    """Draws the batteries, big and small."""
    from PIL import ImageGrab

    root = tk.Tk()
    root.configure(bg=BG_CARD)
    root.geometry("1180x820+40+40")
    root.attributes("-topmost", True)
    root.lift()
    root.focus_force()

    family = "Microsoft YaHei UI"
    shots = []

    for name, width, height, size in SIZES:
        heading = tk.Label(root, text=name, bg=BG_CARD, fg="#98A0AE",
                           font=(family, 9))
        heading.pack(anchor="w", padx=16, pady=(10, 0))

        # The real size.
        row = tk.Frame(root, bg=BG_CARD)
        row.pack(fill="x", pady=2, padx=16)
        for percent, charging in CASES:
            canvas = tk.Canvas(row, bg=BG_CARD, highlightthickness=0, bd=0,
                               width=width, height=height)
            canvas.pack(side="left", padx=(0, 10))
            text = "--" if percent is None else f"{percent}%"
            draw_battery(canvas, 0, 0, width, height, percent, charging,
                         text=text, font=(family, size, "bold"))

        # The same battery, blown up.
        big = tk.Frame(root, bg=BG_CARD)
        big.pack(fill="x", pady=2, padx=16)
        for percent, charging in CASES:
            canvas = tk.Canvas(big, bg=BG_CARD, highlightthickness=0, bd=0,
                               width=width * ZOOM, height=height * ZOOM)
            canvas.pack(side="left", padx=(0, 10))
            text = "--" if percent is None else f"{percent}%"
            draw_battery(canvas, 0, 0, width * ZOOM, height * ZOOM, percent,
                         charging, text=text,
                         font=(family, size * ZOOM, "bold"))
            shots.append(canvas)

    for _ in range(40):
        root.update()
        time.sleep(0.02)

    root.lift()
    root.update()
    time.sleep(0.3)
    root.update()

    # Every battery is grabbed on its own, so the picture is exact.
    out_dir = Path(__file__).resolve().parent.parent
    for index, canvas in enumerate(shots):
        x = canvas.winfo_rootx()
        y = canvas.winfo_rooty()
        image = ImageGrab.grab(bbox=(x, y, x + canvas.winfo_width(),
                                     y + canvas.winfo_height()))
        image.save(out_dir / f"_batt_{index}.png")

    image = ImageGrab.grab(bbox=(root.winfo_rootx(), root.winfo_rooty(),
                                 root.winfo_rootx() + root.winfo_width(),
                                 root.winfo_rooty() + root.winfo_height()))
    out = out_dir / "_battery.png"
    image.save(out)
    print("saved", out, image.size)

    root.destroy()


if __name__ == "__main__":
    main()
