"""Dark title bar and window backdrop for Windows.

The window of the app is dark, but the title bar of Windows is white
unless the app asks for something else. Windows 11 can give the window a
translucent backdrop, so the title bar does not stand out as a bright
strip.

Every function here is optional: on systems that do not know the
attributes, the calls simply fail and the window keeps its normal title
bar.
"""

from __future__ import annotations

import ctypes
import sys


# The attributes of the "window attributes" of DWM.
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_SYSTEMBACKDROP_TYPE = 38

# The kinds of backdrop Windows 11 knows.
DWMSBT_NONE = 1
DWMSBT_MAINWINDOW = 2      # Mica
DWMSBT_TRANSIENTWINDOW = 3  # Acrylic

# The corners of the frame of the window, used to round the window.
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2

# The backdrop of a window is only drawn when the window itself is not
# layered and has no shadow of its own.
DWMWA_TRANSITIONS_FORCEDISABLED = 3


def apply_dark_titlebar(hwnd: int) -> bool:
    """Paints the title bar in the dark colours of the app.

    Returns True when the title bar was painted.
    """
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        dwmapi = ctypes.WinDLL("dwmapi")
    except (AttributeError, OSError):
        return False
    value = ctypes.c_int(1)
    result = dwmapi.DwmSetWindowAttribute(
        ctypes.c_void_p(hwnd),
        ctypes.c_int(DWMWA_USE_IMMERSIVE_DARK_MODE),
        ctypes.byref(value),
        ctypes.sizeof(value))
    return result == 0


def apply_backdrop(hwnd: int, kind: int = DWMSBT_TRANSIENTWINDOW) -> bool:
    """Gives the window the translucent material of Windows 11.

    The title bar then shows the blurred background instead of a solid
    colour. Returns True when the backdrop was set.
    """
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        dwmapi = ctypes.WinDLL("dwmapi")
    except (AttributeError, OSError):
        return False
    value = ctypes.c_int(kind)
    result = dwmapi.DwmSetWindowAttribute(
        ctypes.c_void_p(hwnd),
        ctypes.c_int(DWMWA_SYSTEMBACKDROP_TYPE),
        ctypes.byref(value),
        ctypes.sizeof(value))
    return result == 0


def apply_rounded_corners(hwnd: int) -> bool:
    """Rounds the corners of the window."""
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        dwmapi = ctypes.WinDLL("dwmapi")
    except (AttributeError, OSError):
        return False
    value = ctypes.c_int(DWMWCP_ROUND)
    result = dwmapi.DwmSetWindowAttribute(
        ctypes.c_void_p(hwnd),
        ctypes.c_int(DWMWA_WINDOW_CORNER_PREFERENCE),
        ctypes.byref(value),
        ctypes.sizeof(value))
    return result == 0


def frame_handle(root) -> int:
    """Returns the handle of the frame of a Tk window.

    Tkinter gives the handle of the inner window, but the title bar
    belongs to the frame around it.
    """
    try:
        frame = root.wm_frame()
    except Exception:
        return 0
    if not frame:
        return 0
    try:
        return int(frame, 16)
    except (TypeError, ValueError):
        return 0


def style_window(root, backdrop: bool = False) -> None:
    """Gives a Tk window a dark title bar.

    The title bar of Windows is white by default, which does not fit to the
    dark window. Windows 11 can paint it in the dark colours of the app.

    The call is made again when the window is drawn, because the window
    handle only exists after the window was shown.
    """
    if sys.platform != "win32":
        return

    def _style() -> None:
        hwnd = frame_handle(root)
        if not hwnd:
            return
        apply_dark_titlebar(hwnd)
        apply_rounded_corners(hwnd)
        if backdrop:
            apply_backdrop(hwnd, DWMSBT_TRANSIENTWINDOW)

    # The first time the window is mapped, the frame exists.
    root.after_idle(_style)
    root.after(200, _style)
    root.after(600, _style)
