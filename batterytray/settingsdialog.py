"""A settings dialog for the application options.

The dialog lets the user change the options that used to require editing the
config file by hand: which kinds of peripherals are shown, how often the
devices are polled, and when the low battery notification fires.

The window follows the main window: the same dark background, green accent
and rounded cards, and the same pixel sized text. It can be resized freely;
the cards move to a second column as soon as the window is wide enough, and
everything that does not fit is scrolled with the wheel or with the scroll
bar on the right.
"""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import font as tkfont

from .config import Config
from .dialog import prepare_dialog
from .dpi import scale_pixels
from .widgets import (
    ACCENT,
    BG,
    BG_BORDER,
    BG_CARD,
    BG_DIVIDER,
    BG_FIELD,
    BG_SCROLL,
    BG_SCROLL_HANDLE,
    FG,
    FG_DIM,
    FG_MUTED,
    GlassButton,
    draw_rounded_rect,
    rounded_points,
)

# The kinds of peripheral the user can switch on or off.
KIND_LABELS = [
    ("mouse", "鼠标"),
    ("headset", "耳机"),
    ("controller", "游戏手柄"),
    ("keyboard", "键盘"),
]

# The most groups of options that fit next to each other.
MAX_COLUMNS = 2

# The ink of the marks that are drawn on the badge.
BADGE_INK = "#20252C"


def pick_font_family(root: tk.Misc) -> str:
    """Chooses the best UI font available on this system."""
    available = set(tkfont.families(root))
    for name in ("Microsoft YaHei UI", "Segoe UI", "Tahoma"):
        if name in available:
            return name
    return "TkDefaultFont"


def _badge(canvas: tk.Canvas, size: float, color: str, mark: str) -> None:
    """Draws the round badge of the heading.

    The mark is drawn as a shape and not as a letter, because a font does
    not have to bring the glyph along.
    """
    canvas.delete("all")
    inset = size * 0.06
    canvas.create_polygon(
        rounded_points(inset, inset, size - inset, size - inset,
                       size / 2 - inset),
        fill=color, outline="")

    middle = size / 2
    if mark == "sliders":
        # Three bars with a knob on each of them.
        for index, offset in enumerate((-0.18, 0.0, 0.18)):
            y = middle + size * offset
            canvas.create_line(size * 0.24, y, size * 0.76, y,
                               fill=BADGE_INK, width=max(2, size * 0.07),
                               capstyle="round")
            knob = size * 0.09
            knob_x = size * (0.36 + 0.10 * (index % 2))
            canvas.create_oval(knob_x - knob, y - knob,
                               knob_x + knob, y + knob,
                               fill=BADGE_INK, outline="")
    else:
        # A gear, drawn as a ring with a few teeth.
        outer = size * 0.34
        inner = size * 0.16
        canvas.create_oval(middle - outer, middle - outer,
                           middle + outer, middle + outer,
                           outline=BADGE_INK, width=max(2, size * 0.07))
        canvas.create_oval(middle - inner, middle - inner,
                           middle + inner, middle + inner,
                           fill=BADGE_INK, outline="")
        for angle in range(0, 360, 60):
            rad = math.radians(angle)
            x1 = middle + math.cos(rad) * outer * 0.95
            y1 = middle + math.sin(rad) * outer * 0.95
            x2 = middle + math.cos(rad) * outer * 1.28
            y2 = middle + math.sin(rad) * outer * 1.28
            canvas.create_line(x1, y1, x2, y2, fill=BADGE_INK,
                               width=max(2, size * 0.08), capstyle="round")


class _Card(tk.Canvas):
    """A card with rounded corners that holds a group of options.

    The rows are put in a frame that is embedded in the canvas, the way the
    device cards of the main window are built: the canvas paints the shape
    and the frame keeps the widgets. :meth:`refresh` sizes the card to its
    rows once they are in place.
    """

    def __init__(self, master: tk.Misc, dpi: float, padding: int = 14,
                 radius: int = 13):
        super().__init__(master, bg=BG, highlightthickness=0, bd=0, height=1)
        self.padding = scale_pixels(padding, dpi)
        self.radius = scale_pixels(radius, dpi)
        self.body = tk.Frame(self, bg=BG_CARD)
        self._window = self.create_window(self.padding, self.padding,
                                          anchor="nw", window=self.body)
        self.bind("<Configure>", self._on_configure)

    def refresh(self) -> None:
        """Sizes the card to the rows inside it.

        A window that is embedded in a canvas does not grow on its own when
        rows are added to it, so the height is asked for once the card is
        filled.
        """
        self.update_idletasks()
        rows_height = self.body.winfo_reqheight()
        self.itemconfigure(self._window,
                           width=max(1, self.winfo_width() - 2 * self.padding),
                           height=rows_height)
        needed = rows_height + 2 * self.padding
        if int(self.cget("height")) != needed:
            self.configure(height=needed)

    def _on_configure(self, event) -> None:
        """Paints the shape for the current size."""
        width = max(1, event.width)
        height = max(1, event.height)
        self.itemconfigure(self._window,
                           width=max(1, width - 2 * self.padding))
        self.delete("bg")
        draw_rounded_rect(self, 0, 0, width, height, self.radius,
                          fill=BG_CARD, tags="bg")
        self.tag_lower("bg")


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
        # The window can be resized like the main window. The minimum keeps
        # the heading and the buttons readable, the canvas scrolls the rest.
        self.resizable(True, True)
        self.minsize(scale_pixels(420, dpi), scale_pixels(340, dpi))
        self.geometry(f"{scale_pixels(640, dpi)}x{scale_pixels(600, dpi)}")
        prepare_dialog(self, master)

        self._gap = scale_pixels(12, dpi)
        # The groups of options, in the order they are shown.
        self._blocks: list[tk.Frame] = []
        # The cards of those groups, so they can size themselves to the rows.
        self._cards: list[_Card] = []
        # How many groups sit next to each other.
        self._columns = 0
        # Set while a relayout waits for the event loop, so it starts once.
        self._relayout_pending = False

        self._build(config)

        self.bind("<Return>", lambda _event: self._confirm())
        self.bind("<Escape>", lambda _event: self._cancel())
        # The wheel is bound to the whole window, because the pointer may
        # rest on a card, a label or a check box while the user scrolls.
        self.bind("<MouseWheel>", self._on_mousewheel)
        self.bind("<Button-4>", self._on_mousewheel)
        self.bind("<Button-5>", self._on_mousewheel)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self.update_idletasks()
        self._layout_blocks()
        self._update_scrollbar()
        self._centre()
        # The keyboard belongs to the dialog, so Escape and Return work
        # without clicking into the window first.
        self.after_idle(self.focus_set)

    # -- building -------------------------------------------------------

    def _build(self, config: Config) -> None:
        """Builds the heading, the scrollable groups and the buttons."""
        dpi = self.dpi
        s = lambda px: scale_pixels(px, dpi)  # noqa: E731
        f = lambda px: -scale_pixels(px, dpi)  # noqa: E731

        # ---- The heading with the round badge ----
        header = tk.Frame(self, bg=BG, height=s(64))
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        badge = tk.Canvas(header, bg=BG, highlightthickness=0, bd=0,
                          width=s(40), height=s(40))
        badge.pack(side="left", padx=(s(18), 0), pady=s(12))
        _badge(badge, s(40), ACCENT, "gear")

        heading = tk.Frame(header, bg=BG)
        heading.pack(side="left", padx=(s(12), 0), fill="x", expand=True)
        tk.Label(heading, text="设置", bg=BG, fg=FG,
                 font=(self.family, f(15), "bold"),
                 anchor="w").pack(anchor="w")
        tk.Label(heading, text="调整 BatteryTray 的显示与提醒方式",
                 bg=BG, fg=FG_MUTED, font=(self.family, f(9)),
                 anchor="w").pack(anchor="w", pady=(s(1), 0))

        tk.Frame(self, bg=BG_DIVIDER, height=1).pack(fill="x", side="top")

        # ---- The scrollable body ----
        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=True)
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_columnconfigure(1, weight=0, minsize=0)
        wrap.grid_rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0, bd=0,
                                height=s(120))
        self.scrollbar = tk.Scrollbar(wrap, orient="vertical",
                                      command=self.canvas.yview,
                                      width=s(10), troughcolor=BG,
                                      bg=BG_SCROLL, activebackground=BG_SCROLL_HANDLE,
                                      bd=0, highlightthickness=0)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.grid(row=0, column=0, sticky="nsew",
                         padx=(s(18), s(6)), pady=(s(12), 0))
        self.scrollbar.grid(row=0, column=1, sticky="ns",
                            padx=(0, s(4)), pady=(s(12), 0))
        # The bar only helps when the groups do not fit.
        self.scrollbar.grid_remove()

        self.inner = tk.Frame(self.canvas, bg=BG)
        self._inner_id = self.canvas.create_window((0, 0), window=self.inner,
                                                   anchor="nw")
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self._blocks = [
            self._kind_block(config),
            self._threshold_block(config),
            self._interval_block(config),
            self._tray_block(config),
            self._diagnostic_hint(),
        ]
        # A card does not grow by itself inside a canvas, so every card is
        # told how tall its rows made it before the window is laid out.
        for card in self._cards:
            card.refresh()

        # ---- The buttons ----
        tk.Frame(self, bg=BG_DIVIDER, height=1).pack(fill="x", side="bottom")
        footer = tk.Frame(self, bg=BG, height=s(50))
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        GlassButton(footer, "保存", self.family, dpi,
                    command=self._confirm, accent=True,
                    background=BG).pack(side="right", padx=(0, s(18)),
                                        pady=s(10))
        GlassButton(footer, "取消", self.family, dpi,
                    command=self._cancel,
                    background=BG).pack(side="right", padx=(0, s(10)),
                                        pady=s(10))
        # The report is the way out for a user who sees no device at all,
        # so the button sits in the footer where it is always in sight.
        GlassButton(footer, "诊断", self.family, dpi,
                    command=self._open_diagnostic,
                    background=BG).pack(side="left", padx=s(18),
                                        pady=s(10))

    def _new_block(self, title: str, hint: str) -> tuple[tk.Frame, _Card]:
        """Adds the heading of a group of options and an empty card."""
        s = lambda px: scale_pixels(px, self.dpi)  # noqa: E731
        f = lambda px: -scale_pixels(px, self.dpi)  # noqa: E731

        block = tk.Frame(self.inner, bg=BG)
        tk.Label(block, text=title, bg=BG, fg=FG,
                 font=(self.family, f(12), "bold"),
                 anchor="w").pack(fill="x")
        if hint:
            tk.Label(block, text=hint, bg=BG, fg=FG_MUTED,
                     font=(self.family, f(9)),
                     anchor="w").pack(fill="x", pady=(s(2), 0))

        card = _Card(block, self.dpi)
        card.pack(fill="both", expand=True, pady=(s(8), 0))
        self._cards.append(card)
        return block, card

    def _row(self, card: _Card, first: bool = False) -> tk.Frame:
        """Adds a row to a card, with a divider above every row but the first."""
        s = lambda px: scale_pixels(px, self.dpi)  # noqa: E731
        if not first:
            tk.Frame(card.body, bg=BG_DIVIDER, height=1).pack(
                fill="x", padx=s(14))
        row = tk.Frame(card.body, bg=BG_CARD)
        row.pack(fill="x", padx=s(14), pady=s(9))
        return row

    def _check(self, row: tk.Frame, text: str, var: tk.BooleanVar) -> tk.Checkbutton:
        """Adds a check box that reads like the text of the main window."""
        s = lambda px: scale_pixels(px, self.dpi)  # noqa: E731
        box = tk.Checkbutton(row, text=text, variable=var, bg=BG_CARD,
                             fg=FG, activebackground=BG_CARD,
                             activeforeground=FG, selectcolor=BG_FIELD,
                             highlightthickness=0, bd=0, cursor="hand2",
                             font=(self.family, -s(11)), anchor="w")
        box.pack(side="left")
        return box

    def _spin(self, row: tk.Frame, var: tk.IntVar, low: int, high: int,
              step: int) -> tk.Spinbox:
        """Adds a number field; the wheel scrolls the page over it."""
        s = lambda px: scale_pixels(px, self.dpi)  # noqa: E731
        field = tk.Spinbox(
            row, from_=low, to=high, width=6, increment=step,
            textvariable=var, bg=BG_FIELD, fg=FG, insertbackground=ACCENT,
            relief="flat", bd=0, highlightthickness=1,
            highlightbackground=BG_BORDER, highlightcolor=ACCENT,
            buttonbackground="#2C343C", font=(self.family, -s(11)))
        field.pack(side="left")
        # A spin box would change its number when the wheel turns. The
        # dialog wants the wheel to scroll the page instead, so the wheel
        # is taken from the field before the class binding sees it.
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            field.bind(sequence, self._wheel_on_field)
        return field

    # -- the groups of options ------------------------------------------

    def _kind_block(self, config: Config) -> tk.Frame:
        """The kinds of peripheral that are shown."""
        block, card = self._new_block("显示的设备类型",
                                      "勾选的类型才会出现在列表和托盘里")
        self.kind_vars: dict[str, tk.BooleanVar] = {}
        enabled = config.kinds
        for index, (kind, label) in enumerate(KIND_LABELS):
            var = tk.BooleanVar(value=kind in enabled)
            self.kind_vars[kind] = var
            self._check(self._row(card, first=index == 0), label, var)
        return block

    def _threshold_block(self, config: Config) -> tk.Frame:
        """The low battery threshold and its notification."""
        block, card = self._new_block("低电量提醒",
                                      "电量低于或等于该值时弹出通知")
        f = lambda px: -scale_pixels(px, self.dpi)  # noqa: E731
        row = self._row(card, first=True)
        self.threshold_var = tk.IntVar(value=config.low_battery_threshold)
        self.threshold_spin = self._spin(row, self.threshold_var, 1, 100, 5)
        tk.Label(row, text="阈值（%）", bg=BG_CARD, fg=FG_DIM,
                 font=(self.family, f(10))).pack(
                     side="left", padx=(scale_pixels(10, self.dpi), 0))

        self.notify_var = tk.BooleanVar(value=config.notify_low_battery)
        self._check(self._row(card), "启用低电量通知", self.notify_var)
        return block

    def _interval_block(self, config: Config) -> tk.Frame:
        """How often the devices are asked for their charge."""
        block, card = self._new_block("轮询间隔", "设备多久被问一次电量")
        f = lambda px: -scale_pixels(px, self.dpi)  # noqa: E731
        row = self._row(card, first=True)
        self.interval_var = tk.IntVar(value=config.poll_interval)
        self.interval_spin = self._spin(row, self.interval_var, 15, 3600, 15)
        tk.Label(row, text="秒（15–3600）", bg=BG_CARD, fg=FG_DIM,
                 font=(self.family, f(10))).pack(
                     side="left", padx=(scale_pixels(10, self.dpi), 0))
        return block

    def _tray_block(self, config: Config) -> tk.Frame:
        """What the tray icon shows."""
        block, card = self._new_block("托盘图标", "托盘里显示什么")
        self.every_var = tk.BooleanVar(value=config.show_every_device)
        self._check(self._row(card, first=True), "显示所有设备的电量",
                    self.every_var)
        self.disconnected_var = tk.BooleanVar(value=config.hide_disconnected)
        self._check(self._row(card), "隐藏未连接的设备", self.disconnected_var)
        return block

    def _diagnostic_hint(self) -> tk.Frame:
        """A line that points to the report in the footer.

        A machine that shows no device at all gives no clue what went
        wrong, so the report says what every driver answered. The button
        that opens it sits in the footer, where it is always in sight.
        """
        block = tk.Frame(self.inner, bg=BG)
        tk.Label(block, text="设备读不到时，用下方的「诊断」按钮"
                 "把报告发给我。", bg=BG, fg=FG_MUTED,
                 font=(self.family, -scale_pixels(9, self.dpi)),
                 anchor="w", justify="left").pack(fill="x")
        return block

    def _open_diagnostic(self) -> None:
        """Shows the window with the diagnostic report."""
        from .diagnosticdialog import ask_diagnostic

        ask_diagnostic(self, self.family, self.dpi)

    # -- the responsive layout ------------------------------------------

    def _column_count(self) -> int:
        """How many groups fit next to each other."""
        width = self.canvas.winfo_width()
        if width <= 1:
            # The canvas has not been laid out yet.
            width = max(1, self.winfo_width() - scale_pixels(46, self.dpi))
        if width <= 1:
            return 1
        # A group needs room for a label and a number field; the gap sits
        # between two columns.
        needed = scale_pixels(290, self.dpi) + self._gap
        return max(1, min(MAX_COLUMNS, width // needed))

    def _layout_blocks(self) -> None:
        """Places the groups in as many columns as fit.

        The window is free to be resized, so the groups move to another
        column as soon as there is room for them, and back when the window
        becomes narrow again.
        """
        columns = self._column_count()
        self._columns = columns

        for column in range(MAX_COLUMNS):
            self.inner.grid_columnconfigure(
                column, weight=1 if column < columns else 0, minsize=0)

        rows = (len(self._blocks) + columns - 1) // columns
        for index, block in enumerate(self._blocks):
            row = index // columns
            column = index % columns
            padx = (0, self._gap) if column < columns - 1 else 0
            pady = (0, self._gap) if row < rows - 1 else 0
            # The group is taken out of the grid and put back in, because
            # Tk leaves the widgets hidden when the columns change.
            block.grid_forget()
            block.grid(row=row, column=column, sticky="nsew",
                       padx=padx, pady=pady)

    def _on_inner_configure(self, _event=None) -> None:
        """Keeps the scrollable area as large as the groups.

        The groups have just been laid out, so this is also the moment to
        decide whether the scroll bar is needed.
        """
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._update_scrollbar()

    def _on_canvas_configure(self, event) -> None:
        """Lets the groups use the full width and re-sorts them if needed."""
        self.canvas.itemconfigure(self._inner_id, width=event.width)
        self._update_scrollbar()
        if self._column_count() == self._columns:
            return
        # The groups cannot be moved while Tk is in the middle of the
        # layout, so the work is put off until the event is over.
        if self._relayout_pending:
            return
        self._relayout_pending = True
        self.after_idle(self._relayout_blocks)

    def _relayout_blocks(self) -> None:
        """Moves the groups to another number of columns."""
        self._relayout_pending = False
        self._layout_blocks()
        # The scroll bar may be needed now, but the layout must not be
        # asked for again from here: this runs inside the event loop.
        self._update_scrollbar()

    def _update_scrollbar(self) -> None:
        """Shows the scroll bar only when the groups do not fit.

        The bar is always placed anew. Placing a widget that is already
        placed does nothing, so it would keep the place it had when the
        window was taller and end up outside of the window.
        """
        self.scrollbar.grid_remove()
        bbox = self.canvas.bbox("all")
        if bbox is None:
            return
        content_height = bbox[3] - bbox[1]
        if content_height > self.canvas.winfo_height():
            self.scrollbar.grid(row=0, column=1, sticky="ns",
                                padx=(0, scale_pixels(4, self.dpi)),
                                pady=(scale_pixels(12, self.dpi), 0))

    # -- the wheel ------------------------------------------------------

    def _on_mousewheel(self, event) -> None:
        """Scrolls the groups with the mouse wheel."""
        if not self._pointer_over_canvas():
            return
        self._scroll(event)

    def _wheel_on_field(self, event):
        """Scrolls the page while the wheel turns over a number field."""
        self._scroll(event)
        # The spin box would change its number without this.
        return "break"

    def _scroll(self, event) -> None:
        """Moves the visible part of the groups."""
        if getattr(event, "num", None) == 4:
            self.canvas.yview_scroll(-2, "units")
            return
        if getattr(event, "num", None) == 5:
            self.canvas.yview_scroll(2, "units")
            return

        delta = getattr(event, "delta", 0)
        if not delta:
            return
        if self.canvas.bbox("all") is None:
            return
        top = self.canvas.yview()[0]
        bottom = self.canvas.yview()[1]
        if top <= 0 and bottom >= 1:
            # Everything is visible, there is nothing to scroll.
            return
        # A notch of the wheel is 120 units on Windows.
        steps = int(-delta / 120) * 2 or (-2 if delta > 0 else 2)
        self.canvas.yview_scroll(steps, "units")

    def _pointer_over_canvas(self) -> bool:
        """Whether the pointer is over the scrollable part of the window."""
        x = self.winfo_pointerx()
        y = self.winfo_pointery()
        left = self.canvas.winfo_rootx()
        top = self.canvas.winfo_rooty()
        return (left <= x < left + self.canvas.winfo_width()
                and top <= y < top + self.canvas.winfo_height())

    # -- placing --------------------------------------------------------

    def _centre(self) -> None:
        """Places the dialog in the middle of the screen.

        A window that would not fit on a small screen is made smaller; the
        groups are scrolled in that case, so nothing is lost.
        """
        import ctypes

        self.update_idletasks()
        user32 = ctypes.WinDLL("user32")
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)

        width = self.winfo_width()
        height = self.winfo_height()
        if width <= 1:
            width = self.winfo_reqwidth()
        if height <= 1:
            height = self.winfo_reqheight()
        width = min(width, int(screen_w * 0.9))
        height = min(height, int(screen_h * 0.85))

        x = (screen_w - width) // 2
        y = (screen_h - height) // 3
        self.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")

    # -- the result -----------------------------------------------------

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
