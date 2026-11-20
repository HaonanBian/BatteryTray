"""Checks whether the auto resize breaks the layout of the window.

The window grows by itself to fit the cards. This script resizes the
window with and without that behaviour and compares the result.
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


def report(window, label):
    """Prints the geometry of the sections."""
    print(f"   {label}: window={window.winfo_width()}x{window.winfo_height()}")
    for child in window.winfo_children():
        if child.winfo_class() == "Frame":
            print(f"        {child.winfo_geometry()}")


def scenario(with_devices: bool) -> None:
    """Resizes the window, with or without devices in it."""
    window = BatteryWindow(FakeApp())
    window.geometry("900x700")
    settle(window)
    if with_devices:
        window.set_devices([
            Device("Razer Viper V3 Pro Wireless", 87, kind="mouse")])
        settle(window)

    print(f"=== with_devices={with_devices}")
    report(window, "at 900x700")
    window.geometry("700x500")
    settle(window)
    report(window, "asked 700x500")
    window.destroy()


def main() -> None:
    """Runs both scenarios."""
    scenario(False)
    scenario(True)


if __name__ == "__main__":
    main()
