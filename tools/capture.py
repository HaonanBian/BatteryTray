"""Takes a picture of a window, without asking the screen for it.

The screen is not asked for the picture, because another window may be
lying on top of the one that is wanted. The window is asked to draw
itself into a picture instead.

    python tools/capture.py <window>
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes


class _BITMAPINFOHEADER(ctypes.Structure):
    """The head of the description of a picture."""

    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


def grab(window, own_handle: bool = False):
    """Returns a picture of the window itself.

    The parts of the window that are covered by another window are in
    the picture as well, because the window is asked to draw itself. Set
    ``own_handle`` for a child widget: the frame of a Toplevel belongs to
    the parent, but the picture of a child list should start at the child.
    """
    from PIL import Image

    window.update_idletasks()
    user32 = ctypes.windll.user32
    gdi = ctypes.windll.gdi32

    handle = window.winfo_id()
    if not own_handle:
        handle = user32.GetParent(handle) or handle
    width = window.winfo_width()
    height = window.winfo_height()
    if width <= 1 or height <= 1:
        raise ValueError("the window has no size yet")

    window_dc = user32.GetWindowDC(handle)
    memory_dc = gdi.CreateCompatibleDC(window_dc)
    bitmap = gdi.CreateCompatibleBitmap(window_dc, width, height)
    gdi.SelectObject(memory_dc, bitmap)

    # The flag 2 draws the whole window, the covered parts as well.
    user32.PrintWindow(handle, memory_dc, 2)

    header = _BITMAPINFOHEADER()
    header.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
    header.biWidth = width
    header.biHeight = -height
    header.biPlanes = 1
    header.biBitCount = 32
    header.biCompression = 0

    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi.GetDIBits(memory_dc, bitmap, 0, height, buffer,
                  ctypes.byref(header), 0)

    gdi.DeleteObject(bitmap)
    gdi.DeleteDC(memory_dc)
    user32.ReleaseDC(handle, window_dc)

    return Image.frombuffer("RGB", (width, height), buffer, "raw",
                             "BGRX", 0, 1)
