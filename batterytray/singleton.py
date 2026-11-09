"""Single-instance guard using a named mutex."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt

MUTEX_NAME = "Local\\BatteryTray-single-instance"
ERROR_ALREADY_EXISTS = 183


def acquire() -> "SingleInstance | None":
    """Tries to become the only running instance.

    Returns ``None`` when another instance already holds the mutex.
    """
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = wt.HANDLE
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, ctypes.c_wchar_p]
    kernel32.CloseHandle.argtypes = [wt.HANDLE]

    handle = kernel32.CreateMutexW(None, True, MUTEX_NAME)
    if not handle:
        return None
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return None
    return SingleInstance(handle, kernel32)


class SingleInstance:
    """Holds the mutex for as long as the app runs."""

    def __init__(self, handle: wt.HANDLE, kernel32):
        self._handle = handle
        self._kernel32 = kernel32

    def release(self) -> None:
        """Releases the mutex and closes the handle."""
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self) -> "SingleInstance":
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()
