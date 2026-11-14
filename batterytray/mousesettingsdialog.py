"""The mouse settings dialog.

Lets the user read and change the configuration of a mouse: the DPI, the
polling rate, the DPI stages and the button mapping. Everything is written
to the mouse's own memory, so the settings survive a reboot and work on
another PC.

Two protocols are supported. The Razer mice use the feature report
protocol of :mod:`batterytray.drivers.mouseconfig`, the ASUS ROG mice use
the HID protocol of :mod:`batterytray.drivers.asusmouse`. The two differ
enough that they keep their own driver, but they expose the same
interface, so the dialog does not have to care which one it is talking to.

The dialog is opened from the mouse card in the main window.
"""

from __future__ import annotations

import threading
import tkinter as tk
from dataclasses import dataclass
from tkinter import font as tkfont

from .drivers import mouseadapter, mouseconfig
from .drivers.mouseconfig import (
    DpiStage,
    MOUSE_BUTTON_IDS,
    MouseAsleepError,
    MouseConfigError,
    MouseController,
)
from .dwm import style_window
from .dpi import scale_font, scale_pixels

BG = "#111113"
BG_CARD = "#1C1D20"
BG_FIELD = "#101113"
BG_BORDER = "#2E3035"
FG = "#EDEDED"
FG_DIM = "#9C9EA3"
FG_MUTED = "#6A6C71"
ACCENT = "#00E676"
ACCENT_DARK = "#00A854"
DANGER = "#F44336"
WARNING = "#FFB300"

# The DPI values the picker offers. The mouse accepts any value from 100 to
# 35000, so the entry also accepts a typed number.
DPI_PRESETS = (400, 800, 1600, 3200, 6400, 12800, 25600)


@dataclass(frozen=True)
class ButtonOption:
    """One choice the button dropdown offers.

    The kind decides how the choice is written to the mouse: a default
    restores the factory behaviour, a code assigns the click of another
    mouse button, and a function writes one of the other function ids.
    """

    kind: str
    function_id: int = 0
    code: int = 0


def pick_font_family(root: tk.Misc) -> str:
    """Chooses the best UI font available on this system."""
    available = set(tkfont.families(root))
    for name in ("Microsoft YaHei UI", "Segoe UI", "Tahoma"):
        if name in available:
            return name
    return "TkDefaultFont"


class ConfirmDialog(tk.Toplevel):
    """Asks the user to confirm something that cannot be undone.

    The dialog of Tkinter is white and does not fit to the dark window it
    would open on top of, so the question is asked in a small window of
    the same colour instead.
    """

    def __init__(self, master: tk.Misc, family: str, dpi: float,
                 title: str, message: str, confirm_text: str = "确定"):
        super().__init__(master)
        self.dpi = dpi
        self.family = family
        self.result = False

        self.title(title)
        self.configure(bg=BG)
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.transient(master)
        style_window(self)

        s = lambda px: scale_pixels(px, dpi)  # noqa: E731
        f = lambda pt: scale_font(pt, dpi)  # noqa: E731

        tk.Label(self, text=message, bg=BG, fg=FG,
                 font=(family, f(9)), justify="left",
                 wraplength=s(300)).pack(anchor="w", padx=s(20),
                                         pady=(s(20), s(16)))

        buttons = tk.Frame(self, bg=BG)
        buttons.pack(fill="x", padx=s(20), pady=(0, s(18)))

        tk.Button(buttons, text="取消", bg="#24262A", fg=FG_DIM,
                  activebackground="#2E3136", activeforeground=FG,
                  relief="flat", bd=0, cursor="hand2",
                  font=(family, f(9)),
                  command=self._cancel).pack(side="right")

        tk.Button(buttons, text=confirm_text, bg=DANGER, fg="#FFFFFF",
                  activebackground="#FF5548", activeforeground="#FFFFFF",
                  relief="flat", bd=0, cursor="hand2",
                  font=(family, f(9), "bold"),
                  command=self._confirm).pack(side="right",
                                              padx=(0, s(8)))

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

    def _confirm(self) -> None:
        """Agrees to the action."""
        self.result = True
        self.destroy()

    def _cancel(self) -> None:
        """Refuses the action."""
        self.result = False
        self.destroy()


def ask_confirm(master: tk.Misc, family: str, dpi: float, title: str,
                message: str, confirm_text: str = "确定") -> bool:
    """Asks the user a yes or no question.

    Returns ``True`` when the user agreed.
    """
    dialog = ConfirmDialog(master, family, dpi, title, message, confirm_text)
    master.wait_window(dialog)
    return dialog.result


class MouseSettingsDialog(tk.Toplevel):
    """The mouse configuration window."""

    def __init__(self, master: tk.Misc, device_name: str, product_id: int | None,
                 family: str, dpi: float):
        super().__init__(master)
        self.dpi = dpi
        self.family = family
        self.product_id = product_id
        # The name of the device, needed to pick the right driver when the
        # mouse is opened.
        self.device_name = device_name
        self.controller: mouseadapter.MouseAdapter | None = None
        self._settings: mouseadapter.MouseSettings | None = None
        self._busy = False
        # Set when the dialog is closed while the mouse is still being read.
        self._closed = False
        # The stage and button rows are rebuilt when the mouse answers.
        self._stage_vars: list[tk.IntVar] = []
        self._stage_rows: list[tk.Frame] = []
        self._active_stage = 0
        self._active_var = tk.IntVar(value=0)
        self._button_rows: list[tuple[int, tk.Frame, tk.StringVar]] = []

        self.title(f"鼠标设置 — {device_name}")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.attributes("-topmost", True)
        # The title bar of Windows is white and does not fit to the dark
        # dialog.
        style_window(self)
        self.transient(master)

        self._build()
        self.update_idletasks()
        self._centre()
        # Reading the mouse takes a moment, so it happens off the UI thread.
        self.after(60, self._load_async)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self) -> None:
        """Builds the dialog layout."""
        s = lambda px: self._scale(px)  # noqa: E731

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=s(20), pady=s(16))

        # ---- Status line ----
        self.status_label = tk.Label(body, text="正在读取鼠标设置…", bg=BG,
                                     fg=FG_DIM, font=(self.family, self._f(8)),
                                     anchor="w")
        self.status_label.pack(fill="x")

        # ---- DPI ----
        tk.Frame(body, bg="#232428", height=1).pack(fill="x", pady=s(12))
        tk.Label(body, text="DPI 灵敏度", bg=BG, fg=FG,
                 font=(self.family, self._f(10), "bold")).pack(anchor="w")

        dpi_row = tk.Frame(body, bg=BG)
        dpi_row.pack(fill="x", pady=(s(8), 0))

        self.dpi_var = tk.IntVar(value=1600)
        self.dpi_spin = tk.Spinbox(
            dpi_row, from_=mouseconfig.MIN_DPI, to=mouseconfig.MAX_DPI,
            increment=50, width=8, textvariable=self.dpi_var,
            bg=BG_FIELD, fg=FG, insertbackground=ACCENT, relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BG_BORDER,
            highlightcolor=ACCENT, buttonbackground=BG_CARD,
            font=(self.family, self._f(10)))
        self.dpi_spin.pack(side="left")

        tk.Label(dpi_row, text=f"范围 {mouseconfig.MIN_DPI}–"
                               f"{mouseconfig.MAX_DPI}",
                 bg=BG, fg=FG_MUTED,
                 font=(self.family, self._f(8))).pack(side="left",
                                                        padx=(s(10), 0))

        presets = tk.Frame(body, bg=BG)
        presets.pack(fill="x", pady=(s(6), 0))
        for value in DPI_PRESETS:
            btn = tk.Button(presets, text=str(value), bg=BG_CARD, fg=FG_DIM,
                            activebackground="#2E3136", activeforeground=ACCENT,
                            relief="flat", bd=0, cursor="hand2",
                            font=(self.family, self._f(8)),
                            command=lambda v=value: self.dpi_var.set(v))
            btn.pack(side="left", padx=(0, s(5)))

        # ---- Polling rate ----
        tk.Frame(body, bg="#232428", height=1).pack(fill="x", pady=s(12))
        tk.Label(body, text="回报率", bg=BG, fg=FG,
                 font=(self.family, self._f(10), "bold")).pack(anchor="w")

        poll_row = tk.Frame(body, bg=BG)
        poll_row.pack(fill="x", pady=(s(8), 0))
        self.poll_var = tk.StringVar(value="1000 Hz")
        # A plain OptionMenu keeps the dark theme; the ttk Combobox would need
        # a full restyle of the dropdown list. OptionMenu accepts almost no
        # options at construction, so everything is set afterwards.
        self.poll_menu = tk.OptionMenu(poll_row, self.poll_var, ["1000 Hz"])
        self.poll_menu.configure(
            bg=BG_FIELD, fg=FG, activebackground="#2E3136",
            activeforeground=ACCENT, relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BG_BORDER,
            highlightcolor=ACCENT, font=(self.family, self._f(9)),
            indicatoron=True, anchor="w")
        # The dropdown list needs its own menu to pick up the dark colours.
        dropdown = tk.Menu(self.poll_menu, tearoff=0,
                           bg=BG_FIELD, fg=FG, activebackground="#2E3136",
                           activeforeground=ACCENT, relief="flat", bd=0,
                           font=(self.family, self._f(9)))
        self.poll_menu["menu"] = dropdown
        self.poll_menu.pack(side="left")
        self.poll_hint = tk.Label(poll_row, text="", bg=BG, fg=FG_MUTED,
                                  font=(self.family, self._f(8)))
        self.poll_hint.pack(side="left", padx=(s(10), 0))

        # ---- DPI stages ----
        tk.Frame(body, bg="#232428", height=1).pack(fill="x", pady=s(12))
        stages_header = tk.Frame(body, bg=BG)
        stages_header.pack(fill="x")
        tk.Label(stages_header, text="DPI 挡位", bg=BG, fg=FG,
                 font=(self.family, self._f(10), "bold")).pack(side="left")
        tk.Label(stages_header,
                 text=f"鼠标上的 DPI 键最多 {mouseconfig.MAX_DPI_STAGES} 档",
                 bg=BG, fg=FG_MUTED,
                 font=(self.family, self._f(8))).pack(side="left",
                                                        padx=(s(10), 0))

        self.stages_box = tk.Frame(body, bg=BG_CARD)
        self.stages_box.pack(fill="x", pady=(s(8), 0))
        self.stages_placeholder = tk.Label(
            self.stages_box, text="读取中…", bg=BG_CARD, fg=FG_MUTED,
            font=(self.family, self._f(8)))
        self.stages_placeholder.pack(pady=s(8))

        # ---- Button mapping ----
        tk.Frame(body, bg="#232428", height=1).pack(fill="x", pady=s(12))
        tk.Label(body, text="按键映射", bg=BG, fg=FG,
                 font=(self.family, self._f(10), "bold")).pack(anchor="w")
        tk.Label(body, text="鼠标自带的按键，在下面改成别的功能",
                 bg=BG, fg=FG_MUTED,
                 font=(self.family, self._f(8))).pack(anchor="w",
                                                        pady=(s(2), 0))

        self.buttons_box = tk.Frame(body, bg=BG_CARD)
        self.buttons_box.pack(fill="x", pady=(s(8), 0))
        self.buttons_placeholder = tk.Label(
            self.buttons_box, text="读取中…", bg=BG_CARD, fg=FG_MUTED,
            font=(self.family, self._f(8)))
        self.buttons_placeholder.pack(pady=s(8))

        # ---- Buttons ----
        tk.Frame(self, bg="#232428", height=1).pack(fill="x", side="bottom")
        buttons = tk.Frame(self, bg=BG)
        buttons.pack(fill="x", side="bottom", padx=s(20), pady=s(16))

        self.close_button = tk.Button(buttons, text="关闭", bg="#24262A", fg=FG,
                                      activebackground="#2E3136",
                                      activeforeground=FG, relief="flat", bd=0,
                                      cursor="hand2",
                                      font=(self.family, self._f(9)),
                                      command=self._cancel)
        self.close_button.pack(side="right")

        self.apply_button = tk.Button(buttons, text="应用", bg=ACCENT,
                                       fg="#101113", activebackground="#00F07F",
                                       activeforeground="#101113", relief="flat",
                                       bd=0, cursor="hand2",
                                       font=(self.family, self._f(9), "bold"),
                                       command=self._apply)
        self.apply_button.pack(side="right", padx=(0, s(8)))

        # The factory reset sits on the left, away from the buttons the
        # user presses by accident.
        self.factory_button = tk.Button(
            buttons, text="恢复出厂设置", bg="#24262A", fg=DANGER,
            activebackground="#2E3136", activeforeground=DANGER,
            relief="flat", bd=0, cursor="hand2",
            font=(self.family, self._f(9)),
            command=self._ask_factory_reset)
        self.factory_button.pack(side="left")

        self.protocol("WM_DELETE_WINDOW", self._cancel)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _f(self, points: int) -> int:
        """Scales a font size."""
        from .dpi import scale_font

        return scale_font(points, self.dpi)

    def _scale(self, pixels: int) -> int:
        """Scales a pixel measurement."""
        from .dpi import scale_pixels

        return scale_pixels(pixels, self.dpi)

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

    def _set_status(self, text: str, color: str = FG_DIM) -> None:
        """Updates the status line."""
        self.status_label.configure(text=text, fg=color)

    def _set_busy(self, busy: bool) -> None:
        """Enables or disables the buttons while the mouse is talked to."""
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.apply_button.configure(state=state)
        self.close_button.configure(state=state)
        self.factory_button.configure(state=state)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_async(self) -> None:
        """Reads the mouse settings without blocking the UI."""
        def worker():
            controller = None
            try:
                controller = mouseadapter.open_mouse(self.device_name,
                                                     self.product_id)
                if controller is None:
                    self._post(self._load_failed, "没有找到可访问的鼠标")
                    return
                settings = controller.get_settings()
                buttons = controller.list_buttons()
            except mouseadapter.MouseSleeping:
                self._close_quietly(controller)
                self._post(self._load_failed,
                           "鼠标处于休眠状态，请移动鼠标后重新打开此窗口")
                return
            except mouseadapter.MouseSettingsError as exc:
                self._close_quietly(controller)
                self._post(self._load_failed, str(exc))
                return
            except Exception as exc:  # noqa: BLE001 - report anything to the user
                self._close_quietly(controller)
                self._post(self._load_failed, f"读取失败：{exc}")
                return
            self._post(self._load_done, controller, settings, buttons)

        # A second read opens a second handle, so the old one has to go
        # first. Otherwise the mouse stays locked for the rest of the
        # session.
        self._release_controller()
        threading.Thread(target=worker, daemon=True).start()

    def _release_controller(self) -> None:
        """Closes the handle to the mouse, if there is one."""
        if self.controller is not None:
            self.controller.close()
            self.controller = None

    def _post(self, func, *args) -> None:
        """Runs a call on the tkinter thread.

        Tkinter is not thread safe, so the reader thread may not touch
        the widgets itself. The work is handed to the main window, which
        runs it in its own event loop.
        """
        master = self.master
        post = getattr(master, "post", None)
        if post is not None:
            post(func, *args)
            return
        # The dialog is not owned by the main window, so the call has to
        # be scheduled on this window instead.
        self.after(0, func, *args)

    @staticmethod
    def _close_quietly(controller: mouseadapter.MouseAdapter | None) -> None:
        """Releases a handle that is no longer needed."""
        if controller is not None:
            controller.close()

    def _load_done(self, controller: mouseadapter.MouseAdapter,
                   settings: mouseadapter.MouseSettings,
                   buttons: list[mouseadapter.ButtonMapping]) -> None:
        """Fills the dialog with the values read from the mouse."""
        if self._closed:
            # The dialog was closed while the mouse was being read.
            controller.close()
            return
        self.controller = controller
        self._settings = settings
        self._set_busy(False)

        if settings.dpi:
            self.dpi_var.set(settings.dpi)

        rates = settings.supported_rates
        dropdown = tk.Menu(self.poll_menu, tearoff=0,
                           bg=BG_FIELD, fg=FG, activebackground="#2E3136",
                           activeforeground=ACCENT, relief="flat", bd=0,
                           font=(self.family, self._f(9)))
        for rate in rates:
            dropdown.add_radiobutton(label=f"{rate} Hz",
                                     variable=self.poll_var,
                                     value=f"{rate} Hz")
        self.poll_menu["menu"] = dropdown
        if settings.polling_rate:
            self.poll_var.set(f"{settings.polling_rate} Hz")
        elif rates:
            self.poll_var.set(f"{rates[-1]} Hz")
        if len(rates) <= len(mouseconfig.WIRED_POLLING_RATES):
            self.poll_hint.configure(text="有线连接最高 1000 Hz")
        else:
            self.poll_hint.configure(text="8000 Hz 需要 HyperPolling 接收器")

        self._fill_stages(settings.stages)
        self._fill_buttons(buttons)
        self._set_status("设置已读取，修改后点「应用」", FG_DIM)

    def _load_failed(self, message: str) -> None:
        """Shows a failure to read the mouse."""
        self._set_busy(False)
        self._set_status(message, DANGER)
        # The placeholders are gone as soon as the rows have been built,
        # so they only exist while the first read failed. Asking a
        # destroyed widget for its text would raise.
        for placeholder in (self.stages_placeholder, self.buttons_placeholder):
            try:
                placeholder.configure(text="无法读取")
            except tk.TclError:
                pass

    def _fill_stages(self, stages: list[DpiStage]) -> None:
        """Builds the rows that edit the DPI stages."""
        for child in self.stages_box.winfo_children():
            child.destroy()
        self._stage_vars.clear()
        self._stage_rows.clear()

        if not stages:
            tk.Label(self.stages_box, text="这只鼠标不支持 DPI 挡位",
                     bg=BG_CARD, fg=FG_MUTED,
                     font=(self.family, self._f(8))).pack(pady=self._scale(8))
            return

        self._active_stage = 0
        for index, stage in enumerate(stages):
            row = tk.Frame(self.stages_box, bg=BG_CARD)
            row.pack(fill="x", padx=self._scale(12), pady=self._scale(3))

            radio = tk.Radiobutton(
                row, text="", value=index, variable=self._active_var,
                command=self._on_stage_select, bg=BG_CARD, fg=FG,
                activebackground=BG_CARD, activeforeground=ACCENT,
                selectcolor=BG_FIELD, highlightthickness=0, bd=0,
                indicatoron=True, cursor="hand2")
            radio.pack(side="left")

            var = tk.IntVar(value=stage.dpi)
            spin = tk.Spinbox(
                row, from_=mouseconfig.MIN_DPI, to=mouseconfig.MAX_DPI,
                increment=50, width=8, textvariable=var, bg=BG_FIELD, fg=FG,
                insertbackground=ACCENT, relief="flat", bd=0,
                highlightthickness=1, highlightbackground=BG_BORDER,
                highlightcolor=ACCENT, buttonbackground=BG_CARD,
                font=(self.family, self._f(9)))
            spin.pack(side="left")

            tk.Label(row, text="档", bg=BG_CARD, fg=FG_MUTED,
                     font=(self.family, self._f(8))).pack(side="left",
                                                            padx=(self._scale(6), 0))

            self._stage_vars.append(var)
            self._stage_rows.append(row)

    def _fill_buttons(self, buttons: list[mouseadapter.ButtonMapping]) -> None:
        """Builds the rows that edit the button mapping."""
        for child in self.buttons_box.winfo_children():
            child.destroy()
        self._button_rows.clear()

        if not buttons:
            tk.Label(self.buttons_box, text="无法读取按键列表",
                     bg=BG_CARD, fg=FG_MUTED,
                     font=(self.family, self._f(8))).pack(pady=self._scale(8))
            return

        for mapping in buttons:
            button_id = mapping.button_id
            row = tk.Frame(self.buttons_box, bg=BG_CARD)
            row.pack(fill="x", padx=self._scale(12), pady=self._scale(3))
            row.grid_columnconfigure(1, weight=1)

            name = self._button_name(button_id)
            tk.Label(row, text=name, bg=BG_CARD, fg=FG_DIM,
                     font=(self.family, self._f(9)),
                     anchor="w").grid(row=0, column=0, sticky="w",
                                      padx=(0, self._scale(10)))

            # Each button gets its own dropdown so any function can be picked
            # directly, and "默认值" restores the factory behaviour.
            var = tk.StringVar(
                value=self._function_label(button_id, mapping))
            options = self._function_options()

            dropdown = tk.Menu(row, tearoff=0,
                               bg=BG_FIELD, fg=FG,
                               activebackground="#2E3136",
                               activeforeground=ACCENT, relief="flat", bd=0,
                               font=(self.family, self._f(9)))
            for label, option in options.items():
                dropdown.add_command(
                    label=label,
                    command=lambda b=button_id, o=option, sv=var, sl=label:
                    self._choose_button(b, o, sv, sl))

            picker = tk.Menubutton(row, textvariable=var, relief="flat", bd=0,
                                    bg=BG_FIELD, fg=FG,
                                    activebackground="#2E3136",
                                    activeforeground=ACCENT,
                                    highlightthickness=1,
                                    highlightbackground=BG_BORDER,
                                    highlightcolor=ACCENT,
                                    font=(self.family, self._f(9)),
                                    indicatoron=True, anchor="w",
                                    cursor="hand2", menu=dropdown)
            picker.grid(row=0, column=1, sticky="ew")

            self._button_rows.append((button_id, row, var))

        # One button restores every button at once.
        tk.Button(self.buttons_box, text="全部恢复默认", bg=BG_CARD,
                  fg=FG_DIM, activebackground="#2E3136", activeforeground=ACCENT,
                  relief="flat", bd=0, cursor="hand2",
                  font=(self.family, self._f(8)), padx=self._scale(10),
                  pady=self._scale(4),
                  command=self._reset_all_buttons).pack(
                      anchor="w", padx=self._scale(12),
                      pady=(self._scale(6), self._scale(8)))

    def _button_name(self, button_id: int) -> str:
        """The name of a button, taken from the driver of the vendor."""
        if self.controller is not None:
            return self.controller.button_name(button_id)
        return MOUSE_BUTTON_IDS.get(button_id, f"按键 {button_id}")

    def _function_options(self) -> dict[str, ButtonOption]:
        """The functions the dropdown offers, in the order they are shown."""
        if self.controller is None:
            return {}
        options: dict[str, ButtonOption] = {}
        for label, (kind, function_id, code) in \
                self.controller.function_options().items():
            options[label] = ButtonOption(kind=kind, function_id=function_id,
                                          code=code)
        return options

    def _function_label(self, button_id: int,
                        mapping: mouseadapter.ButtonMapping) -> str:
        """The name shown for the function a button currently has.

        A button on its factory default reads back as function id 1 with
        the button code in the data bytes, and is shown as "默认值".
        """
        if mapping.is_default:
            return "默认值"
        options = self._function_options()
        for label, option in options.items():
            if option.kind != "code":
                continue
            code = option.code
            data = mapping.data
            # The Razer mice store the button code in one byte, the ASUS
            # ones in two little endian bytes.
            if data[:1] == bytes([code]) or data[:2] == bytes(
                    [code & 0xFF, (code >> 8) & 0xFF]):
                return label
        return mapping.label

    def _choose_button(self, button_id: int, option: ButtonOption,
                       var: tk.StringVar, label: str) -> None:
        """Handles a choice made in the button dropdown.

        The label is put into the variable first, so the button shows the
        new choice even when the write to the mouse fails.
        """
        var.set(label)
        self._set_button(button_id, option, var)

    def _set_button(self, button_id: int, option: ButtonOption,
                    var: tk.StringVar) -> None:
        """Writes a new function to one button."""
        if self.controller is None:
            return
        try:
            self.controller.set_button(button_id, option.kind,
                                       option.function_id, option.code)
        except mouseadapter.MouseSleeping:
            self._set_status("鼠标休眠了，移动一下再试", WARNING)
            return
        except mouseadapter.MouseSettingsError as exc:
            self._set_status(str(exc), DANGER)
            return

        name = self._button_name(button_id)
        self._set_status(f"{name} 已改为 {var.get()}", ACCENT)

    def _reset_all_buttons(self) -> None:
        """Restores every button to its factory default."""
        if self.controller is None:
            return
        try:
            self.controller.reset_all_buttons()
        except mouseadapter.MouseSleeping:
            self._set_status("鼠标休眠了，移动一下再试", WARNING)
            return
        except mouseadapter.MouseSettingsError as exc:
            self._set_status(str(exc), DANGER)
            return

        for button_id, _row, var in self._button_rows:
            var.set("默认值")
        self._set_status("所有按键已恢复默认", ACCENT)

    # ------------------------------------------------------------------
    # Factory reset
    # ------------------------------------------------------------------

    def _ask_factory_reset(self) -> None:
        """Asks the user to confirm the factory reset.

        The reset cannot be undone, so the user has to confirm it before
        anything is written to the mouse.
        """
        if self.controller is None:
            self._set_status("鼠标没有连接，无法恢复出厂设置", DANGER)
            return

        confirmed = ask_confirm(
            self, self.family, self.dpi, "恢复出厂设置",
            f"确定要把 {self.device_name} 的所有设置恢复出厂吗？\n\n"
            "DPI、回报率、DPI 挡位和全部按键映射都会回到默认值，\n"
            "此操作无法撤销。",
            confirm_text="恢复出厂")
        if confirmed:
            self._reset_to_factory()

    def _reset_to_factory(self) -> None:
        """Writes the factory defaults to the mouse."""
        self._set_busy(True)
        self._set_status("正在恢复出厂设置…")

        def worker():
            try:
                self.controller.reset_to_factory()
            except mouseadapter.MouseSleeping:
                self._post(self._factory_failed,
                           "鼠标休眠了，移动一下再试")
                return
            except mouseadapter.MouseSettingsError as exc:
                self._post(self._factory_failed, str(exc))
                return
            except Exception as exc:  # noqa: BLE001 - report anything to the user
                self._post(self._factory_failed, f"恢复失败：{exc}")
                return
            self._post(self._factory_done)

        threading.Thread(target=worker, daemon=True).start()

    def _factory_done(self) -> None:
        """Shows the result of a successful reset and reloads the values."""
        self._set_busy(False)
        self._set_status("已恢复出厂设置", ACCENT)
        # The mouse holds the new values now, so they are read back and
        # shown again instead of keeping the old ones on screen.
        self.after(60, self._load_async)

    def _factory_failed(self, message: str) -> None:
        """Shows a failed reset."""
        self._set_busy(False)
        self._set_status(message, DANGER)

    # ------------------------------------------------------------------
    # Applying
    # ------------------------------------------------------------------

    def _apply(self) -> None:
        """Writes the changed values to the mouse."""
        if self.controller is None:
            self._set_status("鼠标没有连接，无法写入", DANGER)
            return

        dpi = self._clamped_dpi()
        rate = self._selected_rate()
        stages = self._selected_stages()

        self._set_busy(True)
        self._set_status("正在写入鼠标…")

        def worker():
            try:
                self.controller.apply_settings(dpi=dpi, polling_rate=rate,
                                               stages=stages)
            except mouseadapter.MouseSleeping:
                self._post(self._apply_failed,
                           "鼠标休眠了，移动一下再点「应用」")
                return
            except mouseadapter.MouseSettingsError as exc:
                self._post(self._apply_failed, str(exc))
                return
            except Exception as exc:  # noqa: BLE001 - report anything to the user
                self._post(self._apply_failed, f"写入失败：{exc}")
                return
            self._post(self._apply_done)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_done(self) -> None:
        """Shows the result of a successful write."""
        self._set_busy(False)
        self._set_status(
            f"已应用：{self._clamped_dpi()} DPI · "
            f"{self._selected_rate()} Hz", ACCENT)

    def _apply_failed(self, message: str) -> None:
        """Shows a failed write."""
        self._set_busy(False)
        self._set_status(message, DANGER)

    def _clamped_dpi(self) -> int:
        """The DPI from the entry, forced into the mouse's range."""
        try:
            value = int(self.dpi_var.get())
        except (TypeError, ValueError):
            value = 1600
        return max(mouseconfig.MIN_DPI, min(mouseconfig.MAX_DPI, value))

    def _selected_rate(self) -> int | None:
        """The polling rate from the dropdown."""
        text = str(self.poll_var.get())
        try:
            return int(text.split()[0])
        except (ValueError, IndexError):
            return None

    def _selected_stages(self) -> list[DpiStage] | None:
        """The DPI stages from the entries."""
        stages: list[DpiStage] = []
        for var in self._stage_vars:
            try:
                value = int(var.get())
            except (TypeError, ValueError):
                continue
            value = max(mouseconfig.MIN_DPI, min(mouseconfig.MAX_DPI, value))
            stages.append(DpiStage(dpi=value))
        return stages or None

    def _on_stage_select(self) -> None:
        """Keeps track of the stage the DPI button starts on."""
        self._active_stage = self._active_var.get()

    def _cancel(self) -> None:
        """Closes the dialog."""
        # The reader thread may still be running; when it finishes it hands
        # the controller over, so it is released here as well.
        self._closed = True
        self._release_controller()
        self.destroy()


def ask_mouse_settings(master: tk.Misc, device_name: str,
                       product_id: int | None, family: str,
                       dpi: float) -> None:
    """Shows the mouse settings window and waits for it to close."""
    dialog = MouseSettingsDialog(master, device_name, product_id, family, dpi)
    master.wait_window(dialog)
