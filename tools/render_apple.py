"""Draws the Apple style battery next to the current one.

    python tools/render_apple.py
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
    FG,
    FG_MUTED,
    draw_apple_battery,
    draw_battery,
)

FAMILY = "Microsoft YaHei UI"


def main() -> None:
    """Draws both styles with a few readings."""
    from PIL import ImageGrab

    root = tk.Tk()
    root.configure(bg=BG)
    root.geometry("900x520+30+30")

    readings = [(87, False), (24, False), (100, True), (15, False),
                (None, False)]

    for title, painter in (("当前样式", "old"), ("苹果样式", "apple")):
        tk.Label(root, text=title, bg=BG, fg=FG_MUTED,
                 font=(FAMILY, 11, "bold")).pack(anchor="w", padx=20,
                                                 pady=(12, 4))
        row = tk.Frame(root, bg=BG)
        row.pack(fill="x", padx=20)

        for percent, charging in readings:
            cell = tk.Frame(row, bg=BG)
            cell.pack(side="left", padx=8)
            canvas = tk.Canvas(cell, bg=BG, highlightthickness=0, bd=0,
                               width=160, height=44)
            canvas.pack()
            text = "--" if percent is None else str(percent)
            if painter == "old":
                draw_battery(canvas, 0, 0, 160, 44, percent, charging,
                             text=text, font=(FAMILY, 20, "bold"))
            else:
                draw_apple_battery(canvas, 0, 0, 160, 44, percent, charging,
                                   text=text, font=(FAMILY, 20, "bold"))
            tk.Label(cell, text="--" if percent is None else f"{percent}%",
                     bg=BG, fg=FG_MUTED, font=(FAMILY, 8)).pack()

    for _ in range(30):
        root.update()
        time.sleep(0.02)

    x, y = root.winfo_rootx(), root.winfo_rooty()
    width = root.winfo_width()
    height = root.winfo_height()
    image = ImageGrab.grab(bbox=(x - 6, y - 6, x + width + 6, y + height + 6))
    out = Path(__file__).resolve().parent.parent / "_apple.png"
    image.save(out)
    print("saved", out, image.size)

    root.destroy()


if __name__ == "__main__":
    main()
