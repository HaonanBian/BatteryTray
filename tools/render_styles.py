"""Draws a few battery styles side by side, to pick one.

    python tools/render_styles.py
"""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batterytray.dpi import set_dpi_aware  # noqa: E402

set_dpi_aware()

import tkinter as tk  # noqa: E402

from batterytray.widgets import BG, FG, FG_MUTED, rounded_points  # noqa: E402

FAMILY = "Microsoft YaHei UI"

# The colours of the styles.
APPLE_GREEN = "#34C759"
APPLE_RED = "#FF3B30"
APPLE_YELLOW = "#FFCC00"
APPLE_BLUE = "#0A84FF"
APPLE_GREY = "#8E8E93"


def apple_color(percent: int | None, charging: bool = False) -> str:
    """The colour of an Apple style battery."""
    if percent is None:
        return APPLE_GREY
    if charging:
        return APPLE_GREEN
    if percent >= 20:
        return APPLE_GREEN
    return APPLE_RED


def style_a(canvas, x, y, w, h, percent, charging):
    """The current style: an outline with the number inside."""
    from batterytray.widgets import draw_battery

    text = "--" if percent is None else str(percent)
    draw_battery(canvas, x, y, w, h, percent, charging, text=text,
                 font=(FAMILY, int(h * 0.5), "bold"))


def style_b(canvas, x, y, w, h, percent, charging):
    """Apple style: a filled pill, no number, a small charging bolt."""
    radius = h / 2
    body_w = w * 0.92
    body_r = x + body_w

    # The outline of the pill.
    canvas.create_polygon(
        rounded_points(x, y, body_r, y + h, radius),
        fill="", outline="#5A5A60", width=max(1, h * 0.055))

    # The contact.
    cw = max(1.5, w * 0.035)
    canvas.create_polygon(
        rounded_points(body_r + w * 0.015, y + h * 0.35,
                       body_r + w * 0.015 + cw, y + h * 0.65, cw * 0.4),
        fill="#5A5A60", outline="")

    if percent is None or percent <= 0:
        return

    # The fill, which is a rounded pill of its own.
    inner = h * 0.11
    fill_w = (body_w - inner * 2) * min(100, percent) / 100
    color = apple_color(percent, charging)
    canvas.create_polygon(
        rounded_points(x + inner, y + inner, x + inner + fill_w, y + h - inner,
                       (h - inner * 2) / 2),
        fill=color, outline="")


def style_c(canvas, x, y, w, h, percent, charging):
    """Apple style with the number inside the pill."""
    radius = h / 2
    body_w = w * 0.92
    body_r = x + body_w

    canvas.create_polygon(
        rounded_points(x, y, body_r, y + h, radius),
        fill="#1C1C1E", outline="#48484A", width=max(1, h * 0.055))

    cw = max(1.5, w * 0.035)
    canvas.create_polygon(
        rounded_points(body_r + w * 0.015, y + h * 0.35,
                       body_r + w * 0.015 + cw, y + h * 0.65, cw * 0.4),
        fill="#48484A", outline="")

    color = apple_color(percent, charging)
    if percent is not None and percent > 0:
        inner = h * 0.11
        fill_w = (body_w - inner * 2) * min(100, percent) / 100
        canvas.create_polygon(
            rounded_points(x + inner, y + inner, x + inner + fill_w,
                           y + h - inner, (h - inner * 2) / 2),
            fill=color, outline="")

    text = "--" if percent is None else f"{percent}%"
    canvas.create_text(x + body_w / 2, y + h / 2, text=text, fill=FG,
                       font=(FAMILY, int(h * 0.52), "bold"))


def style_d(canvas, x, y, w, h, percent, charging):
    """Apple style: a thin pill with a bolt when it is charging."""
    radius = h / 2
    body_w = w * 0.92
    body_r = x + body_w

    canvas.create_polygon(
        rounded_points(x, y, body_r, y + h, radius),
        fill="", outline="#48484A", width=max(1, h * 0.07))

    cw = max(1.5, w * 0.035)
    canvas.create_polygon(
        rounded_points(body_r + w * 0.015, y + h * 0.35,
                       body_r + w * 0.015 + cw, y + h * 0.65, cw * 0.4),
        fill="#48484A", outline="")

    if percent is None or percent <= 0:
        return

    color = apple_color(percent, charging)
    inner = h * 0.14
    fill_w = (body_w - inner * 2) * min(100, percent) / 100
    canvas.create_polygon(
        rounded_points(x + inner, y + inner, x + inner + fill_w, y + h - inner,
                       (h - inner * 2) / 2),
        fill=color, outline="")

    if charging:
        cx = x + body_w / 2
        cy = y + h / 2
        size = h * 0.3
        canvas.create_polygon(
            cx + size * 0.25, cy - size,
            cx - size * 0.35, cy + size * 0.1,
            cx - size * 0.02, cy + size * 0.1,
            cx - size * 0.3, cy + size,
            cx + size * 0.38, cy - size * 0.12,
            cx + size * 0.04, cy - size * 0.12,
            fill="#0B0C10", outline="")


STYLES = [
    ("A 当前样式", style_a),
    ("B 苹果药丸", style_b),
    ("C 药丸+数字", style_c),
    ("D 药丸+闪电", style_d),
]


def main() -> None:
    """Draws every style with a few readings."""
    from PIL import ImageGrab

    root = tk.Tk()
    root.configure(bg=BG)
    root.geometry("980x700+30+30")

    readings = [(87, False), (24, False), (100, True), (15, False),
                (None, False)]

    for name, style in STYLES:
        tk.Label(root, text=name, bg=BG, fg=FG_MUTED,
                 font=(FAMILY, 11, "bold")).pack(anchor="w", padx=20,
                                                 pady=(14, 4))
        row = tk.Frame(root, bg=BG)
        row.pack(fill="x", padx=20)

        for percent, charging in readings:
            cell = tk.Frame(row, bg=BG)
            cell.pack(side="left", padx=10)
            canvas = tk.Canvas(cell, bg=BG, highlightthickness=0, bd=0,
                               width=180, height=46)
            canvas.pack()
            style(canvas, 0, 0, 180, 46, percent, charging)
            tk.Label(cell, text="--" if percent is None else f"{percent}%",
                     bg=BG, fg=FG_MUTED, font=(FAMILY, 8)).pack()

    for _ in range(30):
        root.update()
        time.sleep(0.02)

    x, y = root.winfo_rootx(), root.winfo_rooty()
    width = root.winfo_width()
    height = root.winfo_height()
    image = ImageGrab.grab(bbox=(x - 6, y - 6, x + width + 6, y + height + 6))
    out = Path(__file__).resolve().parent.parent / "_styles.png"
    image.save(out)
    print("saved", out, image.size)

    root.destroy()


if __name__ == "__main__":
    main()
