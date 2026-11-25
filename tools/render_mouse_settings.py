"""Draws the mouse settings window into picture files.

The pictures are only meant for looking at the window while it is being
worked on:

    python tools/render_mouse_settings.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batterytray.dpi import set_dpi_aware  # noqa: E402

set_dpi_aware()

import tkinter as tk  # noqa: E402

from batterytray.mousesettingsdialog import MouseSettingsDialog  # noqa: E402
from batterytray.window import pick_font_family  # noqa: E402

from capture import grab  # noqa: E402


def main() -> int:
    root = tk.Tk()
    root.withdraw()
    family = pick_font_family(root)
    dpi = 96.0

    dialog = MouseSettingsDialog(root, "Razer Viper V3 Pro Wireless", 0x0091,
                                 family, dpi)
    dialog.update_idletasks()
    time.sleep(0.5)
    dialog.update_idletasks()
    grab(dialog).save("out_test/mouse_settings.png")
    print("saved out_test/mouse_settings.png", dialog.winfo_width(),
          dialog.winfo_height())

    # The window has to be resizable, so it is made smaller and bigger.
    for name, size in (("small", "460x400"), ("wide", "900x700"),
                       ("short", "460x260")):
        dialog.geometry(size)
        dialog.update_idletasks()
        time.sleep(0.4)
        dialog.update_idletasks()
        grab(dialog).save(f"out_test/mouse_settings_{name}.png")
        print(f"saved out_test/mouse_settings_{name}.png",
              dialog.winfo_width(), dialog.winfo_height())

    dialog.destroy()
    root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
