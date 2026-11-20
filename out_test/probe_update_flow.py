"""Runs the whole update flow without touching the network.

The window is opened, the check is answered with a fake release and the
result is shown. This proves that the pieces are wired together.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batterytray.dpi import set_dpi_aware  # noqa: E402

set_dpi_aware()

from batterytray.app import Device  # noqa: E402
from batterytray.update import Release  # noqa: E402
from batterytray.window import BatteryWindow  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "out_test"


class FakeApp:
    """Stands in for the tray app."""

    config = None
    calls = []

    def request_refresh(self):
        """The window does not need the real thing."""

    def check_update_async(self, on_result=None, on_error=None):
        """Answers the check with a fake release."""
        FakeApp.calls.append("check_update_async")
        release = Release(
            version="v9.9.9",
            url="https://github.com/HaonanBian/BatteryTray/releases/tag/v9.9.9",
            notes="· 假的新版本，用来测试界面",
            asset_name="BatteryTray-9.9.9.exe",
            asset_url="https://example.invalid/program.exe",
            setup_name="BatteryTray-Setup-9.9.9.exe",
            setup_url="https://example.invalid/setup.exe",
            program_name="BatteryTray-9.9.9.exe",
            program_url="https://example.invalid/program.exe",
        )
        on_result(release)

    def download_update_async(self, release, on_progress=None, on_done=None,
                              on_error=None):
        """Pretends the download worked."""
        FakeApp.calls.append("download_update_async")
        on_progress(50, 100)
        on_progress(100, 100)
        on_done()


def settle(root, rounds=30):
    """Lets Tk finish the layout."""
    for _ in range(rounds):
        root.update_idletasks()
        root.update()
        time.sleep(0.01)


def shot(dialog, name):
    """Saves a screenshot of the dialog."""
    from PIL import ImageGrab
    x, y = dialog.winfo_rootx(), dialog.winfo_rooty()
    w, h = dialog.winfo_width(), dialog.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(OUT / name)
    print("saved", name)


def main() -> None:
    """Runs the flow and takes a screenshot of the result."""
    window = BatteryWindow(FakeApp())
    window.geometry("900x700")
    settle(window)
    window.set_devices([Device("Razer Viper V3 Pro", 87, kind="mouse")])
    settle(window)

    window.open_update_check()
    settle(window)

    # The dialog is the newest toplevel of the window.
    dialog = None
    for child in window.winfo_children():
        if child.winfo_class() == "Toplevel":
            dialog = child
    if dialog is None:
        print("FAIL: no dialog was opened")
        window.destroy()
        return 1

    print("title:", dialog.title_label.cget("text"))
    print("message:", dialog.message_label.cget("text"))
    print("version:", dialog.version_label.cget("text"))
    print("install state:", dialog.install_button.cget("state"))
    print("calls:", FakeApp.calls)
    shot(dialog, "update_flow.png")

    # ---- The install button has to start the download ----
    dialog._install()
    settle(window)
    print("after install, calls:", FakeApp.calls)
    print("after install, title:", dialog.title_label.cget("text"))
    print("after install, message:", dialog.message_label.cget("text"))
    shot(dialog, "update_installing.png")

    # ---- The done callback has to say that it restarts ----
    dialog._on_installed()
    settle(window)
    print("after done, title:", dialog.title_label.cget("text"))
    shot(dialog, "update_restart.png")

    ok = ("check_update_async" in FakeApp.calls
          and "download_update_async" in FakeApp.calls)
    window.destroy()
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
