"""Checks the built executable: the settings window has to open.

The tray menu of the app is a native Windows menu that is opened with a
right click on the tray icon. The check walks the same path the user
takes: the menu is opened and "设置" is picked with the keyboard.

The menu is::

    查看电量
    打开主窗口
    立即刷新
    ---
    设置
    Start with Windows
    打开启动文件夹
    退出
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time
from pathlib import Path

user32 = ctypes.WinDLL("user32", use_last_error=True)
try:
    user32.SetProcessDPIAware()
except Exception:
    pass

WM_NOTIFY = 0x040B
WM_RBUTTONUP = 0x0205
VK_DOWN = 0x28
VK_RETURN = 0x0D
KEYEVENTF_KEYUP = 0x0002
SETTINGS_TITLE = "BatteryTray 设置"

# The number of times the cursor has to move down to reach "设置". The
# separator in the menu is skipped by Windows.
DOWNS_TO_SETTINGS = 4


class RECT(ctypes.Structure):
    _fields_ = [("left", wt.LONG), ("top", wt.LONG),
                ("right", wt.LONG), ("bottom", wt.LONG)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.POINTER(wt.ULONG))]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("padding", ctypes.c_byte * 24)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]


def exe_pids() -> set[int]:
    # The one file build is named after the file it was copied to, so the
    # name of the running process is not always "BatteryTray.exe".
    script = ("Get-CimInstance Win32_Process | "
              "Where-Object { $_.Name -like 'BatteryTray*.exe' } | "
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


def tray_hwnds():
    found = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def enum_proc(hwnd, lparam):
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if "SystemTrayIcon" in cls.value:
            found.append(hwnd)
        return True

    user32.EnumWindows(EnumWindowsProc(enum_proc), 0)
    return found


def press_key(vk: int) -> None:
    """Presses a key once."""
    down = INPUT(type=1)
    down.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0, time=0,
                         dwExtraInfo=None)
    up = INPUT(type=1)
    up.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0,
                       dwExtraInfo=None)
    user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
    user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))


def kill_exes() -> None:
    for pid in exe_pids():
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       capture_output=True, timeout=30)


def main() -> int:
    exe = Path(sys.argv[1] if len(sys.argv) > 1
               else "release/BatteryTray-1.1.0.exe").resolve()
    if not exe.exists():
        print(f"FAIL: {exe} does not exist")
        return 1

    kill_exes()
    time.sleep(1.0)

    print(f"starting {exe.name}")
    subprocess.Popen([str(exe)], cwd=str(exe.parent))

    # The one file build unpacks itself first, so it needs a moment
    # before the windows show up.
    pids: set[int] = set()
    for _ in range(30):
        time.sleep(1.0)
        pids = exe_pids()
        if pids:
            break
    time.sleep(3.0)

    print("exe pids:", pids)
    if not pids:
        print("FAIL: the exe is not running")
        return 1

    windows = find_windows(pids)
    tray = tray_hwnds()
    print("tray icon windows:", len(tray))
    if not tray:
        kill_exes()
        print("FAIL: no tray icon window")
        return 1

    main_hidden = [w for w in windows
                   if w["title"] == "BatteryTray" and not w["visible"]]
    print("main window hidden:", len(main_hidden) > 0)

    # The window of the tray icon has to be allowed to come to the front,
    # otherwise the menu would open behind the other windows.
    for pid in pids:
        user32.AllowSetForegroundWindow(pid)

    # A right click on the tray icon opens the menu. The message is
    # posted, so the call does not block, and the menu is opened by the
    # thread of the icon.
    menu_shown = False
    for hwnd in tray:
        user32.PostMessageW(hwnd, WM_NOTIFY, 0, WM_RBUTTONUP)
        time.sleep(1.5)
        menus = [w for w in find_windows(pids) if w["class"] == "#32768"]
        if menus:
            print(f"menu opened from the tray window {hwnd}: {menus[0]['rect']}")
            menu_shown = True
            break

    if not menu_shown:
        kill_exes()
        print("FAIL: the tray menu did not open")
        return 1

    # The menu is on screen now, so "设置" is picked with a click. The
    # items are stacked, so the position of the item is worked out from
    # the height of the menu.
    menu = [w for w in find_windows(pids) if w["class"] == "#32768"][0]
    left, top, right, bottom = menu["rect"]
    # The menu has eight rows: three items, a separator and four more
    # items. Windows leaves out the separator, so there are seven rows
    # that can be picked.
    rows = 7
    row_height = (bottom - top) / rows
    # "设置" is the fifth item, so the fourth row below the first one.
    x = left + 30
    y = int(top + row_height * 4)
    print(f"clicking 设置 at ({x}, {y})")
    user32.SetForegroundWindow(menu["hwnd"])
    time.sleep(0.3)
    user32.SetCursorPos(x, y)
    time.sleep(0.3)
    mouse_event = user32.mouse_event
    mouse_event(0x0002, 0, 0, 0, 0)   # LEFTDOWN
    time.sleep(0.1)
    mouse_event(0x0004, 0, 0, 0, 0)   # LEFTUP
    time.sleep(3.0)

    windows = find_windows(pids)
    print("\nwindows after picking 设置:")
    for w in windows:
        print(f"  {w['title']!r} class={w['class']} visible={w['visible']} "
              f"rect={w['rect']}")

    settings = [w for w in windows if w["title"] == SETTINGS_TITLE]
    if not settings:
        kill_exes()
        print("\nFAIL: the settings window was not created")
        return 1

    visible = [w for w in settings if w["visible"]]
    if not visible:
        kill_exes()
        print("\nFAIL: the settings window was created but is not visible")
        return 1

    rect = visible[0]["rect"]
    width = rect[2] - rect[0]
    height = rect[3] - rect[1]
    print(f"\nOK: the settings window is visible at {rect} "
          f"({width}x{height})")

    if width < 100 or height < 100:
        kill_exes()
        print("FAIL: the settings window has no size")
        return 1

    kill_exes()
    return 0


if __name__ == "__main__":
    sys.exit(main())
