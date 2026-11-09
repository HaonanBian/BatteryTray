"""DPI helpers.

Windows scales an app that does not declare itself DPI aware: the window is
rendered at the old resolution and then stretched, which makes text look
blurry. Declaring awareness before any window is created makes the UI render
crisply on scaled displays.
"""

from __future__ import annotations

import ctypes
import sys


def set_dpi_aware() -> float:
    """Makes the process per-monitor DPI aware.

    Returns the DPI of the primary display so the caller can size the UI
    accordingly. Safe to call more than once.
    """
    if sys.platform != "win32":
        return 96.0

    user32 = ctypes.WinDLL("user32", use_last_error=True)

    # PER_MONITOR_AWARE_V2 = -4, available on Windows 10 1703 and later.
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return _primary_dpi()
    except (AttributeError, OSError):
        pass

    try:
        # PROCESS_PER_MONITOR_DPI_AWARE = 2
        shcore = ctypes.WinDLL("shcore")
        if shcore.SetProcessDpiAwareness(2) == 0:
            return _primary_dpi()
    except (AttributeError, OSError):
        pass

    try:
        user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass

    return _primary_dpi()


def _primary_dpi() -> float:
    """The DPI of the primary display, defaulting to 96."""
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        dpi = user32.GetDpiForSystem()
        if dpi:
            return float(dpi)
    except (AttributeError, OSError):
        pass
    return 96.0


def scale_font(points: int, dpi: float) -> int:
    """Scales a point size for the given DPI."""
    return max(6, round(points * dpi / 96.0))


def scale_pixels(pixels: int, dpi: float) -> int:
    """Scales a pixel size for the given DPI."""
    return max(1, round(pixels * dpi / 96.0))
