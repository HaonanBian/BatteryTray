"""Prints the sizes of the parts of the tray panel.

    python tools/inspect_panel.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from tkinter import font as tkfont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batterytray.app import Device  # noqa: E402
from batterytray.dpi import set_dpi_aware  # noqa: E402

set_dpi_aware()

from batterytray.window import BatteryWindow  # noqa: E402


class FakeApp:
    """Stands in for the tray app."""

    config = None

    def request_refresh(self):
        """The panel does not need the real thing."""

    def rename_device(self, original, new):
        """The panel does not need the real thing."""


def main() -> None:
    """Prints where the parts of the panel are."""
    window = BatteryWindow(FakeApp())
    window.withdraw()

    panel = window.quick_panel
    panel.set_devices([
        Device("Razer Viper V3 Pro Wireless", 87, kind="mouse"),
        Device("WH-CH720N Hands-Free AG", 24, kind="headset"),
        Device("ROG Keris Wireless Aimpoint", 100, kind="mouse",
               charging=True),
    ])
    window.update()
    window.update_idletasks()
    panel.geometry("+300+200")
    panel.deiconify()
    panel.update()

    label = panel.percent_label
    print("percent label text:", repr(label.cget("text")))
    print("  req width:", label.winfo_reqwidth(),
          "actual width:", label.winfo_width())
    measure = tkfont.Font(root=panel, font=label.cget("font"))
    print("  measured width of the text:", measure.measure(label.cget("text")))
    print("  x:", label.winfo_x(), "y:", label.winfo_y())

    top = panel.winfo_children()[0].winfo_children()[0]
    print("top frame width:", top.winfo_width())
    for child in top.winfo_children():
        print("  ", child.winfo_class(), "x", child.winfo_x(),
              "w", child.winfo_width(), "req", child.winfo_reqwidth())

    panel.destroy()
    window.destroy()


if __name__ == "__main__":
    main()
