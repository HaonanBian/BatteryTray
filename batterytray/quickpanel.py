"""A lightweight popup that shows the battery level of every device.

The panel pops up when the tray icon is clicked. It has no title bar, sits
above the notification area and closes again as soon as the user clicks
somewhere else. The full application window stays available through the
tray menu for anyone who wants the detailed view.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time
import tkinter as tk
from tkinter import font as tkfont

from .dpi import scale_font, scale_pixels

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

# The palette matches the main window.
BG = "#17181B"
BG_BORDER = "#34363B"
BG_ROW = "#1F2124"
BG_ROW_HOVER = "#282A2F"
FG = "#EDEDED"
FG_DIM = "#9C9EA3"
FG_MUTED = "#6A6C71"
ACCENT = "#00E676"
WARNING = "#FFB300"
DANGER = "#F44336"
CHARGING = "#29B6F6"

# Level thresholds, matching icon.py.
HIGH = 60
MEDIUM = 20

# The low level mouse hook reports the down and the up of the left button.
WH_MOUSE_LL = 14
WM_LBUTTONDOWN = 0x0201


class MouseWatcher:
    """Watches the mouse with a global hook.

    The hook is far more reliable than polling the button state: a poll can
    miss a short click, and the reported state can be wrong while the mouse
    sits still.

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
        """Installs the hook."""
        if self._hook is not None:
            return

        def hook(code, wparam, lparam):
            if code >= 0 and wparam == WM_LBUTTONDOWN:
                self.clicked = True
            return user32.CallNextHookEx(self._hook, code, wparam, lparam)

        # The callback has to outlive this call, so it is kept on the object.
        self._procedure = self._hook_type(hook)
        self._hook = user32.SetWindowsHookExW(
            WH_MOUSE_LL, ctypes.cast(self._procedure, ctypes.c_void_p),
            None, 0)
        if not self._hook:
            # The hook could not be installed; the panel then only closes
            # through the tray icon.
            self._procedure = None

    def stop(self) -> None:
        """Removes the hook."""
        if self._hook is not None:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
            self._procedure = None

    def take_click(self) -> bool:
        """Whether a click happened, clearing the flag."""
        if not self.clicked:
            return False
        self.clicked = False
        return True


def level_color(percent: int | None, charging: bool = False) -> str:
    """Colour for a battery level."""
    if percent is None:
        return FG_MUTED
    if charging:
        return CHARGING
    if percent >= HIGH:
        return ACCENT
    if percent >= MEDIUM:
        return WARNING
    return DANGER


def pick_font_family(root: tk.Misc) -> str:
    """Chooses the best UI font available on this system."""
    available = set(tkfont.families(root))
    for name in ("Microsoft YaHei UI", "Segoe UI", "Tahoma"):
        if name in available:
            return name
    return "TkDefaultFont"


class BatteryBar(tk.Canvas):
    """A thin horizontal battery gauge."""

    def __init__(self, master: tk.Misc, width: int, height: int, bg: str):
        super().__init__(master, width=width, height=height, bg=bg,
                         highlightthickness=0)
        self._width = width
        self._height = height
        self._percent: int | None = None
        self._charging = False

        self._trough = self.create_rectangle(0, 0, width, height,
                                             fill="#33353A", outline="")
        self._fill = self.create_rectangle(0, 0, 0, height, fill=ACCENT,
                                           outline="")

    def set_percent(self, percent: int | None, charging: bool = False) -> None:
        """Updates the gauge."""
        self._percent = percent
        self._charging = charging

        if percent is None:
            self.itemconfigure(self._fill, width=0)
            return

        color = level_color(percent, charging)
        filled = int(self._width * max(0, min(100, percent)) / 100)
        self.itemconfigure(self._fill, width=filled, fill=color)


class DeviceRow(tk.Frame):
    """One device in the popup: name, battery bar and percentage."""

    def __init__(self, master: tk.Misc, family: str, dpi: float,
                 on_rename=None):
        super().__init__(master, bg=BG_ROW)
        self.family = family
        self.dpi = dpi
        self.on_rename = on_rename
        self._original_name = ""

        # A row holds three parts side by side; the text block takes the
        # remaining space.
        text = tk.Frame(self, bg=BG_ROW)
        text.pack(side="left", fill="x", expand=True)

        self.name_label = tk.Label(text, text="", bg=BG_ROW, fg=FG,
                                   font=(family, scale_font(9, dpi)), anchor="w")
        self.name_label.pack(anchor="w")
        self.state_label = tk.Label(text, text="", bg=BG_ROW, fg=FG_DIM,
                                    font=(family, scale_font(7, dpi)), anchor="w")
        self.state_label.pack(anchor="w", pady=(1, 0))

        bar_width = scale_pixels(58, dpi)
        bar_height = scale_pixels(6, dpi)
        self.bar = BatteryBar(self, bar_width, bar_height, BG_ROW)
        self.bar.pack(side="left", padx=(scale_pixels(10, dpi), 0),
                      pady=scale_pixels(11, dpi))

        self.percent_label = tk.Label(self, text="--", bg=BG_ROW, fg=FG,
                                      font=(family, scale_font(11, dpi),
                                            "bold"), anchor="e")
        self.percent_label.pack(side="left", padx=(scale_pixels(10, dpi), 0),
                                pady=scale_pixels(9, dpi))

        # Right clicking a row offers to rename the device.
        for widget in (self, text, self.name_label, self.state_label):
            widget.bind("<Button-3>", self._open_rename_menu)

        self._bind_hover()

    def _open_rename_menu(self, event=None) -> None:
        """Shows the context menu with the rename option."""
        if self.on_rename is None:
            return
        menu = tk.Menu(self, tearoff=0, bg=BG_ROW, fg=FG,
                       activebackground=ACCENT, activeforeground="#101113",
                       font=(self.family, scale_font(9, self.dpi)))
        menu.add_command(label="重命名设备",
                         command=lambda: self.on_rename(self._original_name))
        try:
            menu.tk_popup(event.x_root if event else self.winfo_rootx(),
                          event.y_root if event else self.winfo_rooty())
        finally:
            menu.grab_release()

    def _bind_hover(self) -> None:
        """Highlights the row when the pointer is over it."""
        widgets = [self, self.name_label, self.state_label, self.percent_label,
                   self.bar]

        def enter(_event=None):
            for widget in widgets:
                if widget is not self.bar:
                    widget.configure(bg=BG_ROW_HOVER)
            self.bar.configure(bg=BG_ROW_HOVER)

        def leave(_event=None):
            for widget in widgets:
                if widget is not self.bar:
                    widget.configure(bg=BG_ROW)
            self.bar.configure(bg=BG_ROW)

        for widget in widgets:
            widget.bind("<Enter>", enter)
            widget.bind("<Leave>", leave)

    def update(self, device) -> None:
        """Refreshes the row with a new reading."""
        self._original_name = getattr(device, "original_name", device.name)
        self.name_label.configure(text=device.name)
        self.bar.set_percent(device.percent, device.charging)

        if device.percent is None:
            self.percent_label.configure(text="--", fg=FG_MUTED)
        else:
            self.percent_label.configure(
                text=f"{device.percent}%",
                fg=level_color(device.percent, device.charging))

        if device.charging:
            self.state_label.configure(text="充电中", fg=CHARGING)
        elif device.percent is None:
            self.state_label.configure(text="未连接", fg=FG_MUTED)
        else:
            self.state_label.configure(text=device.subtitle, fg=FG_DIM)


class QuickPanel(tk.Toplevel):
    """The popup shown when the tray icon is clicked."""

    def __init__(self, master: tk.Misc, on_rename=None):
        super().__init__(master)

        self.dpi = master.dpi
        self.family = master.family
        self.on_rename = on_rename
        self._rows: list[DeviceRow] = []
        self._visible = False
        # The moment the panel was opened; used to ignore the click that
        # opened it.
        self._opened_at = 0.0
        # The mouse hook watches for clicks outside of the panel.
        self._watcher = MouseWatcher()

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=BG_BORDER)
        # A child toplevel inherits the title of its parent; give it its own
        # so the two windows can be told apart.
        self.title("BatteryTray 电量")
        # The panel starts hidden; it only appears when the icon is clicked.
        self.withdraw()

        # An inner frame provides the border; the outer frame is the colour.
        shell = tk.Frame(self, bg=BG_BORDER, bd=0)
        shell.pack(fill="both", expand=True, padx=1, pady=1)

        inner = tk.Frame(shell, bg=BG)
        inner.pack(fill="both", expand=True)

        # ---- Header ----
        header = tk.Frame(inner, bg=BG, height=scale_pixels(34, self.dpi))
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(header, text="电量", bg=BG, fg=FG,
                 font=(self.family, scale_font(9, self.dpi), "bold")
                 ).pack(side="left", padx=scale_pixels(14, self.dpi),
                        pady=scale_pixels(9, self.dpi))
        self.summary_label = tk.Label(header, text="", bg=BG, fg=FG_MUTED,
                                      font=(self.family, scale_font(7, self.dpi)))
        self.summary_label.pack(side="right", padx=scale_pixels(14, self.dpi))

        tk.Frame(inner, bg="#2A2C30", height=1).pack(fill="x")

        # ---- Device rows ----
        self.rows_frame = tk.Frame(inner, bg=BG)
        self.rows_frame.pack(fill="both", expand=True)

        # Clicking the panel itself must not close it.
        for widget in (self, shell, inner, header, self.rows_frame):
            widget.bind("<Button-1>", lambda _event: None)

        self.protocol("WM_DELETE_WINDOW", self.hide)

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------

    def set_devices(self, devices: list) -> None:
        """Rebuilds the device rows.

        Devices that are not connected are left out; they only belong in the
        main window, where the full picture is shown.
        """
        devices = [d for d in devices if getattr(d, "connected", True)]

        # Every child has to go, including the separators; destroying only the
        # rows would leave the separators behind and the panel would grow on
        # every refresh.
        for child in self.rows_frame.winfo_children():
            child.destroy()
        self._rows.clear()

        if not devices:
            tk.Label(self.rows_frame, text="未检测到设备", bg=BG, fg=FG_MUTED,
                     font=(self.family, scale_font(9, self.dpi))).pack(
                         pady=scale_pixels(18, self.dpi))
            self.summary_label.configure(text="")
            return

        # Every row is packed with the same side so the stacking order is
        # the order the rows were added in.
        for index, device in enumerate(devices):
            row = DeviceRow(self.rows_frame, self.family, self.dpi,
                            on_rename=self.on_rename)
            row.update(device)
            row.pack(fill="x", side="top")
            self._rows.append(row)

            if index < len(devices) - 1:
                separator = tk.Frame(self.rows_frame, bg="#242629", height=1)
                separator.pack(fill="x", side="top")

        connected = sum(1 for d in devices if d.percent is not None)
        if connected == len(devices):
            self.summary_label.configure(text=f"{len(devices)} 个设备")
        else:
            self.summary_label.configure(
                text=f"{len(devices)} 个设备 · {connected} 个已连接")

    # ------------------------------------------------------------------
    # Showing and hiding
    # ------------------------------------------------------------------

    def show(self) -> None:
        """Shows the panel next to the notification area."""
        self.update_idletasks()
        width = self.winfo_reqwidth()
        height = self.winfo_reqheight()

        point = wt.POINT()
        user32.GetCursorPos(ctypes.byref(point))

        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)

        # Prefer the area above the icon; fall back to below it when the icon
        # sits at the very top of the screen.
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
        # The click on the tray icon also reaches the hook, so the first
        # moment is ignored to keep the panel from closing right away.
        self._opened_at = time.monotonic()
        self._watcher.start()
        self._watch()

    def hide(self) -> None:
        """Hides the panel."""
        if not self._visible:
            return
        self._visible = False
        self._watcher.stop()
        self.withdraw()

    def toggle(self) -> None:
        """Shows the panel, or hides it when it is already open."""
        if self._visible:
            self.hide()
        else:
            self.show()

    def _watch(self) -> None:
        """Hides the panel when the user clicks outside of it.

        The hook only sets a flag, so the panel is closed from the Tk loop
        instead of from inside the hook.
        """
        if not self._visible:
            return

        if self._watcher.take_click():
            # The click that opened the panel must not close it again.
            if time.monotonic() - self._opened_at > 0.4:
                point = wt.POINT()
                user32.GetCursorPos(ctypes.byref(point))
                if not self._inside(point.x, point.y):
                    self.hide()
                    return

        self.after(50, self._watch)

    def _inside(self, x: int, y: int) -> bool:
        """Whether the point lies inside the panel."""
        left = self.winfo_rootx()
        top = self.winfo_rooty()
        return (left <= x < left + self.winfo_width()
                and top <= y < top + self.winfo_height())