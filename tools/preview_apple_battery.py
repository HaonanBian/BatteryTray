"""Shows the battery styles next to each other.

    python tools/preview_apple_battery.py
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
    BG_CARD,
    FG,
    FG_MUTED,
    draw_apple_battery,
    draw_apple_battery_vertical,
    draw_battery,
)

FAMILY = "Microsoft YaHei UI"


def main() -> None:
    """Paints every style with a few readings."""
    from PIL import ImageGrab

    root = tk.Tk()
    root.configure(bg=BG)
    root.geometry("1000x420+30+30")

    readings = [(87, False), (24, False), (100, True), (15, False),
                (None, False)]

    def column(title: str, painter) -> None:
        """Adds one column of styles."""
        frame = tk.Frame(root, bg=BG)
        frame.pack(side="left", fill="both", expand=True, padx=8, pady=12)
        tk.Label(frame, text=title, bg=BG, fg=FG_MUTED,
                 font=(FAMILY, 10, "bold")).pack(anchor="w", pady=(0, 8))
        for percent, charging in readings:
            cell = tk.Frame(frame, bg=BG_CARD)
            cell.pack(fill="x", pady=3)
            canvas = tk.Canvas(cell, bg=BG_CARD, highlightthickness=0, bd=0,
                               width=260, height=52)
            canvas.pack(side="left", padx=8)
            text = "--" if percent is None else str(percent)
            painter(canvas, percent, charging, text)
            tk.Label(cell, text="--" if percent is None else f"{percent}%",
                     bg=BG_CARD, fg=FG_MUTED,
                     font=(FAMILY, 9)).pack(side="left", padx=6)

    def old(canvas, percent, charging, text):
        draw_battery(canvas, 0, 4, 200, 44, percent, charging, text=text,
                     font=(FAMILY, 20, "bold"))

    def horizontal(canvas, percent, charging, text):
        draw_apple_battery(canvas, 0, 4, 200, 44, percent, charging,
                            text=text, font=(FAMILY, 20, "bold"))

    def vertical(canvas, percent, charging, text):
        draw_apple_battery_vertical(canvas, 10, 0, 40, 52, percent, charging,
                                    text=text, font=(FAMILY, 15, "bold"))

    column("当前样式", old)
    column("苹果横条", horizontal)
    column("苹果竖条 (参考图)", vertical)

    for _ in range(40):
        root.update()
        time.sleep(0.02)

    x, y = root.winfo_rootx(), root.winfo_rooty()
    width = root.winfo_width()
    height = root.winfo_height()
    image = ImageGrab.grab(bbox=(x - 6, y - 6, x + width + 6, y + height + 6))
    out = Path(__file__).resolve().parent.parent / "_preview_apple.png"
    image.save(out)
    print("saved", out, image.size)

    root.destroy()


if __name__ == "__main__":
    main()
