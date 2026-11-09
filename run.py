"""Entry point for the BatteryTray application."""

from __future__ import annotations

import sys


def main() -> int:
    """Starts the tray application."""
    # The DPI awareness has to be declared before any window is created,
    # otherwise Windows stretches the rendered window and the text turns blurry.
    from batterytray.dpi import set_dpi_aware

    set_dpi_aware()

    from batterytray.app import TrayApp

    app = TrayApp()
    if "--show" in sys.argv:
        # Open the main window straight away instead of waiting for the user
        # to click the tray icon.
        app.show_window_on_start = True
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
