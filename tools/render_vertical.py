"""Draws the vertical battery on its own, so it can be seen closely.

    python tools/render_vertical.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batterytray.dpi import set_dpi_aware  # noqa: E402

set_dpi_aware()

import tkinter as tk  # noqa: E402

from batterytray.widgets import (  # noqa: E402
    BG,
    FG_MUTED,
    draw_apple_battery_vertical,
)

FAMILY = "Microsoft YaHei UI"


def main() -> None:
    """Paints the vertical battery with a few readings."""
    from PIL import ImageGrab

    root = tk.Tk()
    root.configure(bg=BG)
    root.geometry("520x300+30+30")

    readings = [(87, False), (24, False), (100, True), (15, False),
                (None, False)]

    row = tk.Frame(root, bg=BG)
    row.pack(fill="both", expand=True, padx=20, pady=20)

    for percent, charging in readings:
        cell = tk.Frame(row, bg=BG)
        cell.pack(side="left", padx=10)
        canvas = tk.Canvas(cell, bg=BG, highlightthickness=0, bd=0,
                           width=70, height=180)
        canvas.pack()
        text = "--" if percent is None else str(percent)
        draw_apple_battery_vertical(canvas, 14, 4, 42, 172, percent, charging,
                                    text=text, font=(FAMILY, 16, "bold"))
        tk.Label(cell, text="--" if percent is None else f"{percent}%",
                 bg=BG, fg=FG_MUTED, font=(FAMILY, 9)).pack()

    for _ in range(40):
        root.update()
        time.sleep(0.02)

    x, y = root.winfo_rootx(), root.winfo_rooty()
    width = root.winfo_width()
    height = root.winfo_height()
    image = ImageGrab.grab(bbox=(x - 6, y - 6, x + width + 6, y + height + 6))
    out = Path(__file__).resolve().parent.parent / "_vertical.png"
    image.save(out)
    print("saved", out, image.size)

    root.destroy()


if __name__ == "__main__":
    main()
