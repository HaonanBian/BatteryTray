"""Draws the diagnostic window into a picture file.

The picture is only meant for looking at the window while it is being
worked on:

    python tools/render_diagnostic.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batterytray.dpi import set_dpi_aware  # noqa: E402

set_dpi_aware()

import tkinter as tk  # noqa: E402

from batterytray.diagnosticdialog import DiagnosticDialog  # noqa: E402
from batterytray.window import pick_font_family  # noqa: E402

from capture import grab  # noqa: E402


def main() -> int:
    root = tk.Tk()
    root.withdraw()
    family = pick_font_family(root)
    dpi = 96.0

    dialog = DiagnosticDialog(root, family, dpi)
    # The report is built a moment after the window opens; the picture is
    # taken once it is there.
    deadline = time.time() + 20
    while time.time() < deadline and dialog.report is None:
        root.update()
        time.sleep(0.1)
    dialog.update_idletasks()
    time.sleep(0.4)
    dialog.update_idletasks()
    grab(dialog).save("out_test/diagnostic.png")
    print("saved out_test/diagnostic.png", dialog.winfo_width(),
          dialog.winfo_height())
    dialog.destroy()
    root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
