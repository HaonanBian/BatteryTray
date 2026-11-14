"""Draws the mouse settings window into a picture file.

The dialog reads the mouse on its own, so a fake controller is injected
instead. The picture shows the layout, which is what has to be checked
after a change to the window.

    python tools/render_mouse_dialog.py
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batterytray.drivers import mouseadapter, mouseconfig  # noqa: E402
from batterytray.dpi import set_dpi_aware  # noqa: E402

set_dpi_aware()

import tkinter as tk  # noqa: E402

from batterytray.mousesettingsdialog import MouseSettingsDialog  # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32")


class RECT(ctypes.Structure):
    _fields_ = [("left", wt.LONG), ("top", wt.LONG),
                ("right", wt.LONG), ("bottom", wt.LONG)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG),
                ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
                ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


def toplevel_hwnd(widget) -> int:
    """The handle of the real window behind a Tk widget.

    ``winfo_id`` returns the child window that Tk draws into, so the
    parents are walked up until the top level one is reached.
    """
    hwnd = widget.winfo_id()
    while True:
        parent = user32.GetParent(hwnd)
        if not parent:
            return hwnd
        hwnd = parent


def capture(hwnd: int, path: Path) -> None:
    """Saves the picture of a window."""
    from PIL import Image

    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        print("bad rect", width, height)
        return

    window_dc = user32.GetWindowDC(hwnd)
    mem_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    gdi32.SelectObject(mem_dc, bitmap)
    # The flag 2 asks for the whole window, title bar included.
    user32.PrintWindow(hwnd, mem_dc, 2)

    header = BITMAPINFOHEADER()
    header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    header.biWidth = width
    header.biHeight = -height
    header.biPlanes = 1
    header.biBitCount = 32
    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(mem_dc, bitmap, 0, height, buffer,
                    ctypes.byref(header), 0)

    Image.frombuffer("RGB", (width, height), buffer, "raw",
                     "BGRX", 0, 1).save(path)
    print("saved", path, (width, height))

    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(hwnd, window_dc)


class FakeController:
    """A mouse that answers with a fixed set of values."""

    def get_settings(self):
        return mouseconfig.MouseSettings(
            dpi_x=3200, dpi_y=3200,
            polling_rate=1000,
            stages=[mouseconfig.DpiStage(dpi=400),
                    mouseconfig.DpiStage(dpi=800),
                    mouseconfig.DpiStage(dpi=1600)],
            active_stage=2)

    def list_buttons(self):
        return [1, 2, 3, 4, 5, 9, 10]

    def get_button_mapping(self, button_id):
        return mouseconfig.ButtonMapping(
            button_id=button_id,
            function_id=mouseconfig.FUNCTION_DEFAULT,
            data=bytes([button_id]))

    @property
    def supported_polling_rates(self):
        return mouseconfig.WIRELESS_POLLING_RATES

    def close(self):
        pass


def main() -> int:
    """Draws the window with the values of a fake mouse in it."""
    root = tk.Tk()
    # The root has to stay visible; a withdrawn master leaves its children
    # unmapped, and an unmapped window has no size.
    root.geometry("200x100+50+50")

    dialog = MouseSettingsDialog(root, "Razer Viper V3 Pro Wireless",
                                 0x00C1, "Microsoft YaHei UI", 96.0)
    # The dialog reads the mouse on its own; the fake is put in afterwards
    # so the picture shows real values.
    fake = FakeController()
    adapter = mouseadapter.MouseAdapter(fake, "razer")
    dialog._load_done(adapter, adapter.get_settings(),
                       adapter.list_buttons())

    dialog.deiconify()
    dialog.update_idletasks()
    for _ in range(40):
        dialog.update()
        time.sleep(0.02)

    capture(toplevel_hwnd(dialog),
            Path(__file__).resolve().parent.parent / "mouse_dialog.png")

    dialog.destroy()
    root.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
