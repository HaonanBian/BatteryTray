"""Finds out why the footer of the main window stops following the window.

The footer is packed at the bottom and the list in the middle, so the
footer should always sit at the bottom of the window. This script prints
what the packer decided at every size.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batterytray.app import Device  # noqa: E402
from batterytray.dpi import set_dpi_aware  # noqa: E402

set_dpi_aware()

from batterytray.window import BatteryWindow  # noqa: E402
from batterytray.widgets import GlassButton  # noqa: E402


class FakeApp:
    """Stands in for the tray app."""

    config = None

    def request_refresh(self):
        """The window does not need the real thing."""

    def rename_device(self, original, new):
        """The window does not need the real thing."""


def settle(window, rounds=40):
    """Lets Tk finish the layout."""
    for _ in range(rounds):
        window.update_idletasks()
        window.update()
        time.sleep(0.005)


def main() -> None:
    """Prints the packing decisions of the window."""
    window = BatteryWindow(FakeApp())
    window.geometry("900x700")
    settle(window)
    window.set_devices([
        Device("Razer Viper V3 Pro Wireless", 87, kind="mouse"),
    ])
    settle(window)

    for width, height in [(900, 700), (700, 500), (600, 400), (540, 390)]:
        window.geometry(f"{width}x{height}")
        settle(window)

        print(f"=== asked {width}x{height}, window is "
              f"{window.winfo_width()}x{window.winfo_height()}")
        for child in window.winfo_children():
            print(f"   {child.winfo_class():10s} "
                  f"manager={child.winfo_manager():6s} "
                  f"geo={child.winfo_geometry():14s} "
                  f"req={child.winfo_reqwidth()}x{child.winfo_reqheight()} "
                  f"parent={child.winfo_parent()}")

        for button in window.winfo_children():
            for sub in button.winfo_children():
                if isinstance(sub, GlassButton):
                    print(f"      BUTTON {sub._text!r} "
                          f"geo={sub.winfo_geometry()} "
                          f"root={sub.winfo_rootx()},{sub.winfo_rooty()} "
                          f"viewable={sub.winfo_viewable()}")

    window.destroy()


if __name__ == "__main__":
    main()
