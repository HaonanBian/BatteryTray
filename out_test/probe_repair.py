"""Finds out which part of the window keeps the footer from moving.

The footer of the main window is packed at the bottom, but it stops
following the window as soon as the window becomes smaller. This script
tries a few repairs at runtime and reports which one works.
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


class FakeApp:
    """Stands in for the tray app."""

    config = None

    def request_refresh(self):
        """The window does not need the real thing."""

    def rename_device(self, original, new):
        """The window does not need the real thing."""


def settle(window, rounds=30):
    """Lets Tk finish the layout."""
    for _ in range(rounds):
        window.update_idletasks()
        window.update()
        time.sleep(0.005)


def footer_of(window):
    """The frame that holds the two buttons."""
    for child in window.winfo_children():
        if child.winfo_class() == "Frame" and child.winfo_height() > 40 \
                and child.winfo_rooty() > window.winfo_rooty() + 100:
            return child
    return None


def report(window, label):
    """Prints where the footer sits."""
    footer = footer_of(window)
    geo = footer.winfo_geometry() if footer else "?"
    print(f"   {label}: window={window.winfo_width()}x{window.winfo_height()} "
          f"footer={geo}")


def main() -> None:
    """Runs the repairs."""
    window = BatteryWindow(FakeApp())
    window.geometry("900x700")
    settle(window)
    window.set_devices([Device("Razer Viper V3 Pro Wireless", 87, kind="mouse")])
    settle(window)

    window.geometry("700x500")
    settle(window)
    report(window, "after resize")
    print("   -> the footer should be at y=457")

    # Repair 1: let the packer arrange everything again.
    print("-- repair 1: update_idletasks on the root")
    window.update_idletasks()
    window.tk.call("update")
    settle(window)
    report(window, "after update")

    # Repair 2: take the footer out and pack it again.
    print("-- repair 2: pack_forget and pack again")
    footer = footer_of(window)
    divider = [c for c in window.winfo_children()
               if c.winfo_class() == "Frame" and c.winfo_height() == 1
               and c.winfo_rooty() > window.winfo_rooty() + 100][0]
    footer.pack_forget()
    divider.pack_forget()
    divider.pack(fill="x", side="bottom")
    footer.pack(fill="x", side="bottom")
    settle(window)
    report(window, "after re-pack")

    window.destroy()


if __name__ == "__main__":
    main()
