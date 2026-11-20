"""Tries repairs for the footer of the real window.

The footer of the main window stops following the window when the window
becomes small. This script applies the candidate repairs to the real
window and reports which one brings the buttons back.
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
    best = None
    for child in window.winfo_children():
        if child.winfo_class() != "Frame":
            continue
        if best is None or child.winfo_rooty() > best.winfo_rooty():
            best = child
    return best


def report(window, label):
    """Prints where the footer sits."""
    footer = footer_of(window)
    print(f"   {label}: window={window.winfo_width()}x{window.winfo_height()} "
          f"footer={footer.winfo_geometry()}")


def run(repair):
    """Applies a repair and resizes the window."""
    window = BatteryWindow(FakeApp())
    window.geometry("900x700")
    settle(window)
    window.set_devices([Device("Razer Viper V3 Pro Wireless", 87, kind="mouse")])
    settle(window)

    repair(window)
    settle(window)

    window.geometry("700x500")
    settle(window)
    report(window, f"repair={repair.__name__}")
    window.destroy()


def repair_none(window):
    """Changes nothing."""


def repair_compress_list(window):
    """Lets the list be squeezed, so the footer keeps its room."""
    window.canvas.pack_propagate(False)


def repair_footer_first(window):
    """Packs the footer before the list."""
    footer = footer_of(window)
    footer.pack_forget()
    footer.pack(fill="x", side="bottom")


def repair_minsize(window):
    """Raises the minimum size of the window."""
    window.minsize(window.winfo_width(), window.winfo_height())


def main() -> None:
    """Runs the repairs."""
    for repair in (repair_none, repair_compress_list, repair_footer_first,
                   repair_minsize):
        run(repair)


if __name__ == "__main__":
    main()
