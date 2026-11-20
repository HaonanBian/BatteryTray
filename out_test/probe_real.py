"""Reproduces the frozen footer with the real widgets of the app.

The window of the app is built from the widgets in ``batterytray.widgets``.
This script builds the same tree with those widgets and checks whether
the footer follows the window.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batterytray.dpi import scale_pixels, set_dpi_aware  # noqa: E402

dpi = set_dpi_aware()
print("dpi:", dpi)

import tkinter as tk  # noqa: E402

from batterytray.widgets import BG, BG_DIVIDER, FG, FG_DIM, GlassButton  # noqa: E402


def settle(root, rounds=30):
    """Lets Tk finish the layout."""
    for _ in range(rounds):
        root.update_idletasks()
        root.update()
        time.sleep(0.005)


def report(root, label):
    """Prints the geometry of the sections."""
    print(f"   {label}: window={root.winfo_width()}x{root.winfo_height()}")
    for child in root.winfo_children():
        if child.winfo_class() == "Frame":
            print(f"        {child.winfo_geometry()}")


def build(root, use_dpi_scale: bool):
    """Builds the layout of the main window."""
    s = (lambda px: scale_pixels(px, dpi)) if use_dpi_scale else (lambda px: px)

    header = tk.Frame(root, bg=BG, height=s(58))
    header.pack(fill="x", side="top")
    header.pack_propagate(False)
    tk.Label(header, text="BatteryTray", bg=BG, fg=FG).pack(side="left",
                                                             padx=s(18))
    tk.Label(header, text="status", bg=BG, fg=FG_DIM).pack(side="right",
                                                           padx=s(18))
    tk.Frame(root, bg=BG_DIVIDER, height=1).pack(fill="x", side="top")

    list_wrap = tk.Frame(root, bg=BG)
    list_wrap.pack(fill="both", expand=True)
    canvas = tk.Canvas(list_wrap, bg=BG, highlightthickness=0, bd=0)
    canvas.grid(row=0, column=0, sticky="nsew", padx=(s(14), s(8)),
                pady=(s(12), 0))
    list_wrap.grid_columnconfigure(0, weight=1)
    list_wrap.grid_rowconfigure(0, weight=1)
    inner = tk.Frame(canvas, bg=BG)
    canvas.create_window((0, 0), window=inner, anchor="nw")

    tk.Frame(root, bg=BG_DIVIDER, height=1).pack(fill="x", side="bottom")
    footer = tk.Frame(root, bg=BG, height=s(42))
    footer.pack(fill="x", side="bottom")
    footer.pack_propagate(False)
    tk.Label(footer, text="summary", bg=BG, fg=FG_DIM).pack(side="left",
                                                            padx=s(18))
    GlassButton(footer, "设置", "Segoe UI", dpi, background=BG).pack(
        side="right", padx=(0, s(10)), pady=s(6))
    GlassButton(footer, "刷新", "Segoe UI", dpi, background=BG).pack(
        side="right", padx=(0, s(18)), pady=s(6))
    return footer


def main() -> None:
    """Runs both variants."""
    for use_dpi_scale in (False, True):
        root = tk.Tk()
        root.geometry("900x700")
        footer = build(root, use_dpi_scale)
        settle(root)
        print(f"=== dpi_scaled={use_dpi_scale}")
        report(root, "900x700")
        root.geometry("700x500")
        settle(root)
        report(root, "700x500")
        root.destroy()


if __name__ == "__main__":
    main()
