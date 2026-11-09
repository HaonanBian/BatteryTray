"""Exercises the rename in the running app and captures the popup."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time

from PIL import Image

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32")
try:
    user32.SetProcessDPIAware()
except Exception:
    pass

POPUP_TITLE = "BatteryTray 电量"
WM_NOTIFY = 0x040B
WM_LBUTTONUP = 0x0202


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


def app_pids() -> set[int]:
    script = ("Get-CimInstance Win32_Process | "
              "Where-Object { $_.Name -eq 'BatteryTray.exe' -or "
              "($_.Name -eq 'python.exe' -and $_.CommandLine -like '*run.py*') } | "
              "Select-Object -ExpandProperty ProcessId")
    out = subprocess.run(["powershell.exe", "-NoProfile", "-Command", script],
                         capture_output=True, text=True, timeout=30)
    return {int(p) for p in out.stdout.split() if p.strip().isdigit()}


def find_windows(pids):
    found = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def enum_proc(hwnd, lparam):
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids:
            title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title, 256)
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            rect = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            found.append({"hwnd": hwnd, "title": title.value,
                          "class": cls.value,
                          "visible": bool(user32.IsWindowVisible(hwnd)),
                          "rect": (rect.left, rect.top, rect.right, rect.bottom)})
        return True

    user32.EnumWindows(EnumWindowsProc(enum_proc), 0)
    return found


def capture(hwnd: int, path: str) -> None:
    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        print("bad rect")
        return

    window_dc = user32.GetWindowDC(hwnd)
    mem_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    gdi32.SelectObject(mem_dc, bitmap)
    user32.PrintWindow(hwnd, mem_dc, 0)

    header = BITMAPINFOHEADER()
    header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    header.biWidth = width
    header.biHeight = -height
    header.biPlanes = 1
    header.biBitCount = 32
    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(mem_dc, bitmap, 0, height, buffer,
                    ctypes.byref(header), 0)

    image = Image.frombuffer("RGB", (width, height), buffer, "raw",
                             "BGRX", 0, 1)
    image.save(path)
    print("saved", path, image.size)

    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(hwnd, window_dc)


def main() -> int:
    pids = app_pids()
    print("app pids:", pids)
    if not pids:
        print("FAIL: the app is not running")
        return 1

    windows = find_windows(pids)
    tray = [w for w in windows if "SystemTrayIcon" in w["class"]]
    print("tray icons:", len(tray))
    for w in tray:
        user32.SendMessageW(w["hwnd"], WM_NOTIFY, 0, WM_LBUTTONUP)
    time.sleep(2.0)

    windows = find_windows(pids)
    popups = [w for w in windows
              if w["visible"] and w["title"] == POPUP_TITLE]
    print("visible popups:", len(popups))
    if popups:
        capture(popups[0]["hwnd"], "panel_pw.png")

    main_windows = [w for w in windows
                    if w["title"] == "BatteryTray" and w["class"] == "TkTopLevel"]
    for w in main_windows:
        print("main window:", w["visible"], w["rect"])
        if w["visible"]:
            capture(w["hwnd"], "main_pw.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
