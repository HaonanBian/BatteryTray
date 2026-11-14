"""The popup that opens from the tray.

The tray itself shows one ring-shaped device icon per device. Clicking any of
those icons opens this slightly larger list: the same ring icon, the device
name, its connection state and the exact percentage. The rows are stacked
vertically, with a separator between them.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time
import tkinter as tk
from tkinter import font as tkfont

from PIL import ImageTk

from .dpi import scale_pixels
from .dwm import apply_rounded_corners, frame_handle
from .icon import build_device_icon

user32 = ctypes.WinDLL("user32", use_last_error=True)

# The hook handles and the callback parameters are 64 bit, so the signatures
# have to be declared; the defaults would truncate them.
user32.CallNextHookEx.argtypes = [
    ctypes.c_void_p, ctypes.c_int, wt.WPARAM, wt.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_longlong
user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int, ctypes.c_void_p, wt.HINSTANCE, wt.DWORD]
user32.SetWindowsHookExW.restype = wt.HHOOK
user32.UnhookWindowsHookEx.argtypes = [wt.HHOOK]
user32.UnhookWindowsHookEx.restype = wt.BOOL

WH_MOUSE_LL = 14
WM_LBUTTONDOWN = 0x0201

PANEL_BG = "#1B2023"
PANEL_BORDER = "#2A3237"
DIVIDER = "#2B3237"
FG = "#F1F3F4"
MUTED = "#9AA3A8"
CHARGING = "#8FC3DF"

PANEL_WIDTH = 340
ROW_HEIGHT = 58
ICON_SIZE = 38


class MouseWatcher:
    """Watches the mouse with a global hook.

    The hook only records that a click happened. Touching Tk from inside the
    hook would re-enter the event loop that is dispatching the hook, so the
    caller has to act on the flag from its own loop.
    """

    def __init__(self):
        self.clicked = False
        self._hook = None
        self._procedure = None
        self._hook_type = ctypes.WINFUNCTYPE(
            ctypes.c_longlong, ctypes.c_int, wt.WPARAM, wt.LPARAM)

    def start(self) -> None:
        if self._hook is not None:
            return

        def hook(code, wparam, lparam):
            if code >= 0 and wparam == WM_LBUTTONDOWN:
                self.clicked = True
            return user32.CallNextHookEx(self._hook, code, wparam, lparam)

        self._procedure = self._hook_type(hook)
        self._hook = user32.SetWindowsHookExW(
            WH_MOUSE_LL, ctypes.cast(self._procedure, ctypes.c_void_p),
            None, 0)
        if not self._hook:
            self._procedure = None

    def stop(self) -> None:
        if self._hook is not None:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
            self._procedure = None

    def take_click(self) -> bool:
        if not self.clicked:
            return False
        self.clicked = False
        return True


def pick_number_family(root: tk.Misc) -> str:
    """The display face for the percentage."""
    available = set(tkfont.families(root))
    for name in ("Segoe UI Variable Display Light", "Segoe UI Light",
                 "Segoe UI", "Tahoma"):
        if name in available:
            return name
    return "TkDefaultFont"


class DeviceRow(tk.Frame):
    """One device in the popup: ring icon, name, status and percentage."""

    def __init__(self, master: tk.Misc, family: str, number_family: str,
                 dpi: float, on_rename=None, on_open=None):
        s = lambda px: scale_pixels(px, dpi)  # noqa: E731
        super().__init__(master, bg=PANEL_BG,
                         width=s(PANEL_WIDTH), height=s(ROW_HEIGHT))
        self.pack_propagate(False)
        self.family = family
        self.number_family = number_family
        self.dpi = dpi
        self.on_rename = on_rename
        self.on_open = on_open
        self._original_name = ""
        self._full_name = ""
        self._kind = "device"
        self._icon_photo = None
        self._icon_key = None
        self._hover = False

        self._name_font = (family, -s(13), "bold")
        self._status_font = (family, -s(10))
        self._percent_font = (number_family, -s(19))
        self._icon_font = ("Segoe MDL2 Assets", -s(12))

        self.icon_label = tk.Label(self, bg=PANEL_BG, bd=0)
        self.icon_label.place(x=s(10), y=s(10))

        self.name_label = tk.Label(
            self, text="", bg=PANEL_BG, fg=FG, font=self._name_font,
            anchor="w")
        self.name_label.place(x=s(58), y=s(8), anchor="nw")

        self.state_label = tk.Label(
            self, text="", bg=PANEL_BG, fg=MUTED, font=self._status_font,
            anchor="w")
        self.state_label.place(x=s(58), y=s(31), anchor="nw")

        self.percent_label = tk.Label(
            self, text="--", bg=PANEL_BG, fg=FG, font=self._percent_font,
            anchor="e")
        self.percent_label.place(relx=1.0, x=-s(14), y=s(8), anchor="ne")

        self.rename_icon = tk.Label(
            self, text="", bg=PANEL_BG, fg=MUTED, font=self._icon_font)
        self.rename_icon.place(relx=1.0, x=-s(14), y=s(31), anchor="ne")
        self.rename_icon.bind("<Button-1>", self._start_rename)

        for widget in (self, self.icon_label, self.name_label,
                       self.state_label, self.percent_label):
            widget.bind("<Button-3>", self._open_rename_menu)
            widget.bind("<Double-Button-1>", self._open_main)
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)

    # ------------------------------------------------------------------
    # Hover
    # ------------------------------------------------------------------

    def _fill(self) -> str:
        return "#222A2E" if self._hover else PANEL_BG

    def _enter(self, _event=None) -> None:
        if self._hover:
            return
        self._hover = True
        for widget in (self, self.icon_label, self.name_label,
                       self.state_label, self.percent_label,
                       self.rename_icon):
            widget.configure(bg=self._fill())

    def _leave(self, _event=None) -> None:
        if not self._hover:
            return
        self._hover = False
        for widget in (self, self.icon_label, self.name_label,
                       self.state_label, self.percent_label,
                       self.rename_icon):
            widget.configure(bg=PANEL_BG)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_main(self, _event=None) -> None:
        if self.on_open is not None:
            self.on_open()

    def _open_rename_menu(self, event=None) -> None:
        if self.on_rename is None:
            return
        menu = tk.Menu(self, tearoff=0, bg="#2A3136", fg=FG,
                       activebackground="#A9D3B6", activeforeground="#142019",
                       font=(self.family, -scale_pixels(9, self.dpi)))
        menu.add_command(label="重命名设备",
                         command=lambda: self.on_rename(self._original_name))
        try:
            menu.tk_popup(event.x_root if event else self.winfo_rootx(),
                          event.y_root if event else self.winfo_rooty())
        finally:
            menu.grab_release()

    def _start_rename(self, _event=None) -> None:
        if self.on_rename is None:
            return
        self.on_rename(self._original_name)

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------

    def update(self, device) -> None:
        """Refreshes the row with a new reading."""
        self._original_name = getattr(device, "original_name", device.name)
        self._full_name = device.name
        self._kind = getattr(device, "kind", "device")

        size = scale_pixels(ICON_SIZE, self.dpi)
        key = (self._kind, size, device.percent, device.charging)
        if key != self._icon_key:
            self._icon_photo = ImageTk.PhotoImage(
                build_device_icon(self._kind, device.percent,
                                  device.charging, device.connected, size=size))
            self._icon_key = key
        self.icon_label.configure(image=self._icon_photo)

        if device.percent is None:
            value, color = "--", MUTED
        else:
            value = f"{device.percent}%"
            color = FG
        self.percent_label.configure(text=value, fg=color)
        self.rename_icon.configure(text="\ue70f")

        if device.charging:
            text, state_color = "充电中", CHARGING
        elif not device.connected or device.percent is None:
            text, state_color = "未连接", MUTED
        else:
            text, state_color = device.subtitle, MUTED
        self.state_label.configure(text=text, fg=state_color)
        self._clip_name()

    def _clip_name(self) -> None:
        """Keeps a long name inside the row, before the percentage."""
        room = scale_pixels(PANEL_WIDTH - 58 - 64, self.dpi)
        measure = tkfont.Font(root=self, font=self._name_font)
        if measure.measure(self._full_name) <= room:
            self.name_label.configure(text=self._full_name)
            return
        for length in range(len(self._full_name) - 1, 0, -1):
            candidate = self._full_name[:length] + "…"
            if measure.measure(candidate) <= room:
                self.name_label.configure(text=candidate)
                return
        self.name_label.configure(text="…")


class QuickPanel(tk.Toplevel):
    """The vertical device list shown when a tray icon is clicked."""

    def __init__(self, master: tk.Misc, on_rename=None, on_open=None):
        super().__init__(master)

        self.dpi = master.dpi
        self.family = master.family
        self.number_family = pick_number_family(self)
        self.on_rename = on_rename
        self.on_open = on_open
        self._rows: list[DeviceRow] = []
        self._visible = False
        self._opened_at = 0.0
        self._watcher = MouseWatcher()

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=PANEL_BORDER)
        self.title("BatteryTray 电量")
        self.withdraw()

        self._panel_width = scale_pixels(PANEL_WIDTH + 2, self.dpi)
        self._panel_height = scale_pixels(ROW_HEIGHT + 2, self.dpi)

        self.rows_frame = tk.Frame(self, bg=PANEL_BG)
        self.rows_frame.pack(fill="both", expand=True, padx=1, pady=1)

        for widget in (self, self.rows_frame):
            widget.bind("<Button-1>", lambda _event: "break")

        self.protocol("WM_DELETE_WINDOW", self.hide)

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------

    def set_devices(self, devices: list) -> None:
        """Rebuilds one row per connected device."""
        devices = [d for d in devices if getattr(d, "connected", True)]

        for child in self.rows_frame.winfo_children():
            child.destroy()
        self._rows.clear()

        if not devices:
            tk.Label(self.rows_frame, text="未检测到设备", bg=PANEL_BG,
                     fg=MUTED,
                     font=(self.family, -scale_pixels(9, self.dpi))).pack(
                         padx=scale_pixels(18, self.dpi),
                         pady=scale_pixels(16, self.dpi))
            self._resize()
            return

        for index, device in enumerate(devices):
            row = DeviceRow(self.rows_frame, self.family, self.number_family,
                            self.dpi, on_rename=self.on_rename,
                            on_open=self.on_open)
            row.update(device)
            row.pack(fill="x")
            self._rows.append(row)
            if index < len(devices) - 1:
                separator = tk.Frame(self.rows_frame, bg=DIVIDER, height=1)
                separator.pack(fill="x", padx=scale_pixels(14, self.dpi))

        self._resize()

    def _resize(self) -> None:
        self.update_idletasks()
        width = scale_pixels(PANEL_WIDTH + 2, self.dpi)
        height = max(scale_pixels(ROW_HEIGHT + 2, self.dpi),
                     self.rows_frame.winfo_reqheight() + 2)
        self._panel_width = width
        self._panel_height = height
        self.geometry(f"{width}x{height}")

    # ------------------------------------------------------------------
    # Showing and hiding
    # ------------------------------------------------------------------

    def show(self) -> None:
        """Shows the list next to the notification area."""
        self.update_idletasks()
        width = self._panel_width
        height = self._panel_height

        point = wt.POINT()
        user32.GetCursorPos(ctypes.byref(point))
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)

        x = point.x - width // 2
        y = point.y - height - scale_pixels(16, self.dpi)
        if y < 0:
            y = point.y + scale_pixels(24, self.dpi)

        margin = scale_pixels(8, self.dpi)
        x = max(margin, min(x, screen_w - width - margin))
        y = max(margin, min(y, screen_h - height - margin))

        self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self._visible = True
        self._round_corners()
        self._opened_at = time.monotonic()
        self._watcher.start()
        self._watch()

    def _round_corners(self) -> None:
        def apply():
            hwnd = frame_handle(self)
            if hwnd:
                apply_rounded_corners(hwnd)

        self.after_idle(apply)
        self.after(120, apply)

    def hide(self) -> None:
        if not self._visible:
            return
        self._visible = False
        self._watcher.stop()
        self.withdraw()

    def toggle(self) -> None:
        if self._visible:
            self.hide()
        else:
            self.show()

    def _watch(self) -> None:
        """Hides the list when the user clicks outside of it."""
        if not self._visible:
            return
        if self._watcher.take_click():
            if time.monotonic() - self._opened_at > 0.4:
                point = wt.POINT()
                user32.GetCursorPos(ctypes.byref(point))
                if not self._inside(point.x, point.y):
                    self.hide()
                    return
        self.after(50, self._watch)

    def _inside(self, x: int, y: int) -> bool:
        left = self.winfo_rootx()
        top = self.winfo_rooty()
        return (left <= x < left + self.winfo_width()
                and top <= y < top + self.winfo_height())
