"""Tries the candidate repairs on the real window.

The footer of the main window stops following the window when the window
becomes small. This script applies the candidate repairs to the real
window and reports the geometry of the footer afterwards.
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


def settle(window, rounds=30):
    """Lets Tk finish the layout."""
    for _ in range(rounds):
        window.update_idletasks()
        window.update()
        time.sleep(0.005)


def buttons_of(window):
    """Every GlassButton of the window."""
    found = []

    def walk(widget):
        for child in widget.winfo_children():
            if isinstance(child, GlassButton):
                found.append(child)
            walk(child)

    walk(window)
    return found


def report(window, label):
    """Prints where the buttons are."""
    window_top = window.winfo_rooty()
    window_bottom = window_top + window.winfo_height()
    print(f"   {label}: window={window.winfo_width()}x{window.winfo_height()}")
    for button in buttons_of(window):
        top = button.winfo_rooty()
        inside = window_top <= top < window_bottom
        print(f"        BUTTON {button._text!r} "
              f"top={top - window_top:4d} inside={inside} "
              f"viewable={button.winfo_viewable()}")


def run(repair):
    """Applies a repair and resizes the window."""
    window = BatteryWindow(FakeApp())
    window.geometry("900x700")
    settle(window)
    window.set_devices([
        Device("Razer Viper V3 Pro Wireless", 87, kind="mouse"),
        Device("Keychron K3 Pro", 42, kind="keyboard"),
    ])
    settle(window)

    repair(window)
    settle(window)

    window.geometry("700x500")
    settle(window)
    report(window, f"repair={repair.__name__}")
    window.destroy()


def repair_none(window):
    """Changes nothing."""


def repair_list_wrap(window):
    """Lets the list be squeezed."""
    window.canvas.master.pack_propagate(False)


def repair_canvas_height(window):
    """Gives the canvas a small height of its own."""
    window.canvas.configure(height=scale_pixels(120, window.dpi))


def scale_pixels(pixels, dpi):
    """Scales a pixel size for the given DPI."""
    return max(1, round(pixels * dpi / 96.0))


def main() -> None:
    """Runs the repairs."""
    for repair in (repair_none, repair_list_wrap, repair_canvas_height):
        run(repair)


if __name__ == "__main__":
    main()
