"""Compares the two candidate repairs for the footer of the window.

The footer of the main window stops following the window when the window
becomes small. Two repairs are tried: giving the canvas a small height
of its own, and packing the footer before the list.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batterytray.app import Device  # noqa: E402
from batterytray.dpi import scale_pixels, set_dpi_aware  # noqa: E402

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
    top = window.winfo_rooty()
    bottom = top + window.winfo_height()
    print(f"   {label}: window={window.winfo_width()}x{window.winfo_height()}")
    for button in buttons_of(window):
        y = button.winfo_rooty()
        print(f"        BUTTON {button._text!r} top={y - top:4d} "
              f"inside={top <= y < bottom} viewable={button.winfo_viewable()}")


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

    for width, height in [(700, 500), (600, 400), (540, 390)]:
        window.geometry(f"{width}x{height}")
        settle(window)
        report(window, f"repair={repair.__name__} asked {width}x{height}")

    window.destroy()


def repair_none(window):
    """Changes nothing."""


def repair_canvas_height(window):
    """Gives the canvas a small height of its own."""
    window.canvas.configure(height=scale_pixels(120, window.dpi))


def repair_footer_first(window):
    """Packs the footer before the list, so it keeps its room."""
    footer = window.footer
    footer.pack_forget()
    footer.pack(fill="x", side="bottom")


def main() -> None:
    """Runs the repairs."""
    for repair in (repair_none, repair_canvas_height, repair_footer_first):
        run(repair)


if __name__ == "__main__":
    main()
