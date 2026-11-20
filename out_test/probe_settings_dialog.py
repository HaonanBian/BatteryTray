"""Renders the settings window.

The window is shown with the settings of the app, so the layout can be
looked at.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batterytray.dpi import set_dpi_aware  # noqa: E402

set_dpi_aware()

import tkinter as tk  # noqa: E402

from batterytray.config import Config  # noqa: E402
from batterytray.settingsdialog import SettingsDialog  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "out_test"


def settle(root, rounds=25):
    """Lets Tk finish the layout."""
    for _ in range(rounds):
        root.update_idletasks()
        root.update()
        time.sleep(0.01)


def main() -> None:
    """Renders the settings window."""
    from PIL import ImageGrab

    OUT.mkdir(exist_ok=True)
    root = tk.Tk()
    root.withdraw()
    family = "Microsoft YaHei UI"

    dialog = SettingsDialog(root, Config(), family, 144.0)
    settle(root)

    x, y = dialog.winfo_rootx(), dialog.winfo_rooty()
    w, h = dialog.winfo_width(), dialog.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(OUT / "settings.png")
    print("saved settings.png", w, h)

    dialog.destroy()
    root.destroy()


if __name__ == "__main__":
    main()
