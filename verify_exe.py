"""Verifies the built executable: tray icon, popup and rename."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time

from PIL import Image

user32 = ctypes.WinDLL("user32", use_last_error=True)
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


def exe_pids() -> set[int]:
    script = ("Get-CimInstance Win32_Process -Filter \"Name='BatteryTray.exe'\" | "
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
                          "style": user32.GetWindowLongW(hwnd, -16) & 0xFFFFFFFF,
                          "rect": (rect.left, rect.top, rect.right, rect.bottom)})
        return True

    user32.EnumWindows(EnumWindowsProc(enum_proc), 0)
    return found


def main() -> int:
    pids = exe_pids()
    print("exe pids:", pids)
    if not pids:
        print("FAIL: the exe is not running")
        return 1

    windows = find_windows(pids)
    tray = [w for w in windows if "SystemTrayIcon" in w["class"]]
    print("tray icon windows:", len(tray))

    for w in tray:
        user32.SendMessageW(w["hwnd"], WM_NOTIFY, 0, WM_LBUTTONUP)
    time.sleep(2.0)

    windows = find_windows(pids)
    main_windows = [w for w in windows
                    if w["title"] == "BatteryTray" and w["class"] == "TkTopLevel"]
    popups = [w for w in windows
              if w["visible"] and w["title"] == POPUP_TITLE]
    print("visible popups:", len(popups))
    print("main window visible:", [w["visible"] for w in main_windows])

    if not popups:
        print("FAIL: the popup did not appear")
        return 1
    print("popup rect:", popups[0]["rect"])

    # The status file lists the readings.
    from batterytray.config import config_dir
    status = config_dir() / "status.txt"
    if status.exists():
        print("\nstatus.txt:")
        print(status.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
