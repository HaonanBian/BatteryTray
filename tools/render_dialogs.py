"""Draws the settings window and the rename window into picture files.

The pictures are only meant for looking at the windows while they are
being worked on:

    python tools/render_dialogs.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batterytray.config import Config  # noqa: E402
from batterytray.dpi import set_dpi_aware  # noqa: E402

set_dpi_aware()

import tkinter as tk  # noqa: E402

from batterytray.renamedialog import RenameDialog  # noqa: E402
from batterytray.settingsdialog import SettingsDialog  # noqa: E402
from batterytray.window import pick_font_family  # noqa: E402

from capture import grab  # noqa: E402


def main() -> int:
    root = tk.Tk()
    root.withdraw()
    family = pick_font_family(root)
    dpi = 96.0

    config = Config()
    config.enabled_kinds = ["mouse", "headset", "controller", "keyboard"]

    settings = SettingsDialog(root, config, family, dpi)
    settings.update_idletasks()
    time.sleep(0.4)
    settings.update_idletasks()
    grab(settings).save("out_test/settings.png")
    print("saved out_test/settings.png", settings.winfo_width(),
          settings.winfo_height())
    settings.destroy()

    rename = RenameDialog(root, family, dpi, "Razer Viper V3 Pro Wireless",
                          "Razer Viper V3 Pro Wireless")
    rename.update_idletasks()
    time.sleep(0.4)
    rename.update_idletasks()
    grab(rename).save("out_test/rename.png")
    print("saved out_test/rename.png", rename.winfo_width(),
          rename.winfo_height())
    rename.destroy()

    root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
