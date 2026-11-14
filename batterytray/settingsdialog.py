"""A settings dialog for the application options.

The dialog lets the user change the options that used to require editing the
config file by hand: which kinds of peripherals are shown, how often the
devices are polled, and when the low battery notification fires.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

from .config import Config
from .dpi import scale_font, scale_pixels
from .dwm import style_window

BG = "#111113"
BG_CARD = "#1C1D20"
BG_FIELD = "#101113"
BG_BORDER = "#2E3035"
FG = "#EDEDED"
FG_DIM = "#9C9EA3"
FG_MUTED = "#6A6C71"
ACCENT = "#00E676"
ACCENT_DARK = "#00A854"

# The kinds of peripheral the user can switch on or off.
KIND_LABELS = [
    ("mouse", "鼠标"),
    ("headset", "耳机"),
    ("controller", "游戏手柄"),
    ("keyboard", "键盘"),
]


def pick_font_family(root: tk.Misc) -> str:
    """Chooses the best UI font available on this system."""
    available = set(tkfont.families(root))
    for name in ("Microsoft YaHei UI", "Segoe UI", "Tahoma"):
        if name in available:
            return name
    return "TkDefaultFont"


class SettingsDialog(tk.Toplevel):
    """The settings window."""

    def __init__(self, master: tk.Misc, config: Config, family: str,
                 dpi: float, on_save=None):
        super().__init__(master)
        self.dpi = dpi
        self.family = family
        self.on_save = on_save
        # The working copy; the config is only replaced when the user saves.
        self.result: Config | None = None
        # The settings the dialog does not show are carried over; they are
        # filled in from the config that was passed in.
        self._autostart = config.autostart
        self._devices = list(config.devices)
        self._custom_names = dict(config.custom_names)

        self.title("BatteryTray 设置")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.transient(master)
        # The title bar of Windows is white and does not fit to the dark
        # dialog.
        style_window(self)

        pad = scale_pixels(20, dpi)
        f = lambda pt: scale_font(pt, dpi)  # noqa: E731
        s = lambda px: scale_pixels(px, dpi)  # noqa: E731

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=pad, pady=pad)

        tk.Label(body, text="显示的设备类型", bg=BG, fg=FG,
                 font=(family, f(10), "bold")).pack(anchor="w")

        tk.Label(body, text="勾选的类型才会出现在列表和托盘里",
                 bg=BG, fg=FG_MUTED,
                 font=(family, f(8))).pack(anchor="w",
                                          pady=(scale_pixels(2, dpi), 0))

        # ---- The device kinds ----
        kinds = tk.Frame(body, bg=BG_CARD)
        kinds.pack(fill="x", pady=(s(10), 0))
        self.kind_vars: dict[str, tk.BooleanVar] = {}
        enabled = config.kinds
        for kind, label in KIND_LABELS:
            var = tk.BooleanVar(value=kind in enabled)
            self.kind_vars[kind] = var
            row = tk.Frame(kinds, bg=BG_CARD)
            row.pack(fill="x", padx=s(12), pady=s(4))
            cb = tk.Checkbutton(row, text=label, variable=var, bg=BG_CARD,
                                fg=FG, activebackground=BG_CARD,
                                activeforeground=FG, selectcolor=BG_FIELD,
                                highlightthickness=0, bd=0,
                                font=(family, f(9)),
                                anchor="w")
            cb.pack(side="left")

        # ---- The low battery threshold ----
        tk.Frame(body, bg="#232428", height=1).pack(fill="x", pady=s(14))

        tk.Label(body, text="低电量提醒阈值（%）", bg=BG, fg=FG,
                 font=(family, f(10), "bold")).pack(anchor="w")

        threshold_row = tk.Frame(body, bg=BG)
        threshold_row.pack(fill="x", pady=(s(8), 0))

        self.threshold_var = tk.IntVar(value=config.low_battery_threshold)
        self.threshold_spin = tk.Spinbox(
            threshold_row, from_=1, to=100, width=6, increment=5,
            textvariable=self.threshold_var, bg=BG_FIELD, fg=FG,
            insertbackground=ACCENT, relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BG_BORDER,
            highlightcolor=ACCENT, buttonbackground=BG_CARD,
            font=(family, f(10)))
        self.threshold_spin.pack(side="left")

        tk.Label(threshold_row, text="电��低于或等于该值时弹出通知",
                 bg=BG, fg=FG_MUTED,
                 font=(family, f(8))).pack(side="left", padx=(s(10), 0))

        # ---- The notification toggle ----
        notify_row = tk.Frame(body, bg=BG)
        notify_row.pack(fill="x", pady=(s(10), 0))
        self.notify_var = tk.BooleanVar(value=config.notify_low_battery)
        tk.Checkbutton(notify_row, text="启用低电量通知", variable=self.notify_var,
                       bg=BG, fg=FG, activebackground=BG,
                       activeforeground=FG, selectcolor=BG_FIELD,
                       highlightthickness=0, bd=0,
                       font=(family, f(9)),
                       anchor="w").pack(side="left")

        # ---- The poll interval ----
        tk.Frame(body, bg="#232428", height=1).pack(fill="x", pady=s(14))

        tk.Label(body, text="轮询间隔（秒）", bg=BG, fg=FG,
                 font=(family, f(10), "bold")).pack(anchor="w")

        interval_row = tk.Frame(body, bg=BG)
        interval_row.pack(fill="x", pady=(s(8), 0))
        self.interval_var = tk.IntVar(value=config.poll_interval)
        self.interval_spin = tk.Spinbox(
            interval_row, from_=15, to=3600, width=6, increment=15,
            textvariable=self.interval_var, bg=BG_FIELD, fg=FG,
            insertbackground=ACCENT, relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BG_BORDER,
            highlightcolor=ACCENT, buttonbackground=BG_CARD,
            font=(family, f(10)))
        self.interval_spin.pack(side="left")
        tk.Label(interval_row, text="范围 15–3600 秒",
                 bg=BG, fg=FG_MUTED,
                 font=(family, f(8))).pack(side="left", padx=(s(10), 0))

        # ---- The show-every-device toggle ----
        every_row = tk.Frame(body, bg=BG)
        every_row.pack(fill="x", pady=(s(10), 0))
        self.every_var = tk.BooleanVar(value=config.show_every_device)
        tk.Checkbutton(every_row, text="托盘图标显示所有设备的电量",
                       variable=self.every_var, bg=BG, fg=FG,
                       activebackground=BG, activeforeground=FG,
                       selectcolor=BG_FIELD, highlightthickness=0, bd=0,
                       font=(family, f(9)),
                       anchor="w").pack(side="left")

        # ---- The hide-disconnected toggle ----
        disconnected_row = tk.Frame(body, bg=BG)
        disconnected_row.pack(fill="x", pady=(s(10), 0))
        self.disconnected_var = tk.BooleanVar(value=config.hide_disconnected)
        tk.Checkbutton(disconnected_row, text="隐藏未连接的设备",
                       variable=self.disconnected_var, bg=BG, fg=FG,
                       activebackground=BG, activeforeground=FG,
                       selectcolor=BG_FIELD, highlightthickness=0, bd=0,
                       font=(family, f(9)),
                       anchor="w").pack(side="left")

        tk.Label(disconnected_row,
                 text="设备列表里不显示离线的设备",
                 bg=BG, fg=FG_MUTED,
                 font=(family, f(8))).pack(side="left", padx=(s(10), 0))

        # ---- Buttons ----
        tk.Frame(self, bg="#232428", height=1).pack(fill="x", side="bottom")
        buttons = tk.Frame(self, bg=BG)
        buttons.pack(fill="x", side="bottom", padx=pad, pady=pad)

        tk.Button(buttons, text="取消", bg="#24262A", fg=FG_DIM,
                  activebackground="#2E3136", activeforeground=FG,
                  relief="flat", bd=0, cursor="hand2",
                  font=(family, f(9)),
                  command=self._cancel).pack(side="right")

        tk.Button(buttons, text="保存", bg=ACCENT, fg="#101113",
                  activebackground="#00F07F", activeforeground="#101113",
                  relief="flat", bd=0, cursor="hand2",
                  font=(family, f(9), "bold"),
                  command=self._confirm).pack(side="right",
                                              padx=(0, scale_pixels(8, dpi)))

        self.bind("<Return>", lambda _event: self._confirm())
        self.bind("<Escape>", lambda _event: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self.update_idletasks()
        self._centre()

    def _centre(self) -> None:
        """Places the dialog in the middle of the screen."""
        import ctypes

        self.update_idletasks()
        width = self.winfo_reqwidth()
        height = self.winfo_reqheight()
        user32 = ctypes.WinDLL("user32")
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
        x = (screen_w - width) // 2
        y = (screen_h - height) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _clamped_threshold(self) -> int:
        """The threshold, forced into a usable range."""
        try:
            value = int(self.threshold_var.get())
        except (TypeError, ValueError):
            return 20
        return max(1, min(100, value))

    def _clamped_interval(self) -> int:
        """The poll interval, forced into a usable range."""
        try:
            value = int(self.interval_var.get())
        except (TypeError, ValueError):
            return 60
        return max(15, min(3600, value))

    def _confirm(self) -> None:
        """Applies the settings and closes the dialog."""
        new_config = Config(
            poll_interval=self._clamped_interval(),
            show_every_device=self.every_var.get(),
            hide_disconnected=self.disconnected_var.get(),
            low_battery_threshold=self._clamped_threshold(),
            notify_low_battery=self.notify_var.get(),
            autostart=self._autostart,
            devices=self._devices,
            custom_names=dict(self._custom_names),
        )
        new_config.set_enabled_kinds(
            [kind for kind, var in self.kind_vars.items() if var.get()])
        self.result = new_config
        self.destroy()

    def _cancel(self) -> None:
        """Closes the dialog without changing anything."""
        self.result = None
        self.destroy()


def ask_settings(master: tk.Misc, config: Config, family: str, dpi: float,
                 on_save=None) -> Config | None:
    """Shows the settings dialog and returns the new config.

    ``None`` means the user cancelled the dialog.
    """
    dialog = SettingsDialog(master, config, family, dpi, on_save)
    master.wait_window(dialog)
    return dialog.result
