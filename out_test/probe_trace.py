"""Traces the layout of the main window while it is resized.

Prints the geometry of the three sections at every step, so it can be
seen which one stops following the window.
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


def show(window, label):
    """Prints the geometry of the sections."""
    parts = []
    for child in window.winfo_children():
        if child.winfo_class() == "Frame":
            parts.append(f"{child.winfo_geometry()}")
    print(f"  {label}: window={window.winfo_width()}x{window.winfo_height()} "
          f"user_resized={window._user_resized} "
          f"resizing={window._resizing} "
          f"last={window._last_size}")
    for geo in parts:
        print(f"       {geo}")


def main() -> None:
    """Resizes the window and prints what happens."""
    window = BatteryWindow(FakeApp())
    window.geometry("900x700")
    settle(window)
    show(window, "initial 900x700")

    print("-- now with devices")
    window.set_devices([
        Device("Razer Viper V3 Pro Wireless", 87, kind="mouse"),
    ])
    settle(window)
    show(window, "after set_devices")

    for width, height in [(700, 500), (600, 400), (540, 390)]:
        print(f"-- resize to {width}x{height}")
        window.geometry(f"{width}x{height}")
        settle(window)
        show(window, f"asked {width}x{height}")

    window.destroy()


if __name__ == "__main__":
    main()
