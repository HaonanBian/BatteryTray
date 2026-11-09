"""The main window: a Razer Synapse inspired dashboard.

The window shows one card per device with a battery ring, the device name,
the connection mode and a set of detail rows. It is themed dark with a green
accent, matching the look of Razer Synapse.
"""

from __future__ import annotations

import queue
import tkinter as tk
from tkinter import font as tkfont

from .dpi import scale_font, scale_pixels, set_dpi_aware

# Razer Synapse-like palette.
BG = "#111113"
BG_CARD = "#1C1D20"
BG_CARD_HOVER = "#24262A"
BG_HEADER = "#0B0B0C"
BG_FOOTER = "#0B0B0C"
FG = "#EDEDED"
FG_DIM = "#9C9EA3"
FG_MUTED = "#6A6C71"
ACCENT = "#00E676"
ACCENT_DARK = "#00A854"
WARNING = "#FFB300"
DANGER = "#F44336"
CHARGING = "#29B6F6"

# Level thresholds, matching icon.py.
HIGH = 60
MEDIUM = 20

# Icon names shown next to a device kind.
KIND_ICONS = {
    "mouse": "MOUSE",
    "headset": "HEADSET",
    "controller": "GAMEPAD",
    "keyboard": "KEYBOARD",
    "device": "DEVICE",
}


def pick_font_family(root: tk.Misc) -> str:
    """Chooses the best UI font available on this system."""
    available = set(tkfont.families(root))
    for name in ("Microsoft YaHei UI", "Segoe UI", "Tahoma"):
        if name in available:
            return name
    return "TkDefaultFont"


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


class BatteryRing(tk.Canvas):
    """A circular battery gauge drawn on a canvas."""

    def __init__(self, master: tk.Misc, size: int = 64, bg: str = BG_CARD):
        super().__init__(master, width=size, height=size, bg=bg,
                         highlightthickness=0)
        self._size = size
        self._percent: int | None = None
        self._charging = False

        pad = max(4, size // 13)
        stroke = max(4, size // 10)
        self._box = self.create_oval(pad, pad, size - pad, size - pad,
                                     outline="#34363B", width=stroke)
        self._arc = self.create_arc(pad, pad, size - pad, size - pad,
                                    start=90, extent=0, style="arc",
                                    outline=ACCENT, width=stroke)
        self._text = self.create_text(size / 2, size / 2, text="--", fill=FG,
                                      font=("Segoe UI", max(9, size // 5),
                                            "bold"))
        self._bolt = self.create_text(size / 2, size / 2 - size // 4, text="⚡",
                                      fill=CHARGING,
                                      font=("Segoe UI Emoji", max(7, size // 8)),
                                      state="hidden")

    def set_background(self, color: str) -> None:
        """Changes the widget background (used for hover effects)."""
        self.configure(bg=color)

    def set_percent(self, percent: int | None, charging: bool = False) -> None:
        """Updates the gauge."""
        self._percent = percent
        self._charging = charging

        if percent is None:
            self.itemconfigure(self._arc, extent=0, outline=FG_MUTED)
            self.itemconfigure(self._text, text="--", fill=FG_MUTED)
            self.itemconfigure(self._bolt, state="hidden")
            return

        color = level_color(percent, charging)
        self.itemconfigure(self._arc, extent=-359.9 * (percent / 100),
                           outline=color)
        self.itemconfigure(self._text, text=f"{percent}%", fill=FG)
        if charging:
            self.itemconfigure(self._bolt, state="normal")
        else:
            self.itemconfigure(self._bolt, state="hidden")


class DeviceCard(tk.Frame):
    """One device: battery ring, name, connection mode and detail rows."""

    def __init__(self, master: tk.Misc, family: str, dpi: float = 96.0,
                 on_click=None, on_rename=None):
        super().__init__(master, bg=BG_CARD, highlightthickness=1,
                         highlightbackground="#2E3035")
        self.family = family
        self.dpi = dpi
        self.on_click = on_click
        self.on_rename = on_rename
        self._percent: int | None = None
        self._charging = False
        self._detail_widgets: list[tk.Widget] = []
        self._editor: tk.Entry | None = None
        self._editor_row: tk.Frame | None = None
        self._original_name = ""

        ring_size = scale_pixels(64, dpi)
        pad_x = scale_pixels(16, dpi)
        gap = scale_pixels(14, dpi)

        # A single column holds the whole card so the detail rows always end
        # up below the summary instead of sharing rows with it.
        body = tk.Frame(self, bg=BG_CARD)
        body.pack(fill="x")
        body.grid_columnconfigure(1, weight=1)

        # Left: the battery ring.
        self.ring = BatteryRing(body, size=ring_size)
        self.ring.grid(row=0, column=0, rowspan=3, padx=(pad_x, gap),
                        pady=scale_pixels(16, dpi))

        # Right: kind, name and status.
        self.kind_label = tk.Label(body, text="", bg=BG_CARD, fg=FG_MUTED,
                                   font=(family, scale_font(7, dpi)), anchor="w")
        self.kind_label.grid(row=0, column=1, sticky="w",
                             pady=(scale_pixels(16, dpi), 0))

        self.name_label = tk.Label(body, text="", bg=BG_CARD, fg=FG,
                                   font=(family, scale_font(10, dpi), "bold"),
                                   anchor="w")
        self.name_label.grid(row=1, column=1, sticky="w")

        self.status_label = tk.Label(body, text="", bg=BG_CARD, fg=FG_DIM,
                                     font=(family, scale_font(8, dpi)), anchor="w")
        self.status_label.grid(row=2, column=1, sticky="w",
                               pady=(scale_pixels(3, dpi), scale_pixels(16, dpi)))

        # The rename button sits on the right of the card.
        self.rename_button = tk.Label(body, text="✎", bg=BG_CARD, fg=FG_MUTED,
                                      font=(family, scale_font(11, dpi)),
                                      cursor="hand2")
        self.rename_button.grid(row=1, column=2, sticky="e",
                                padx=(scale_pixels(8, dpi), scale_pixels(16, dpi)))
        self.rename_button.bind("<Button-1>", self._start_rename)

        self._body = body
        self._bind_hover()

    def _bind_hover(self) -> None:
        """Highlights the card when the pointer is over it."""
        widgets = [self, self._body, self.ring, self.kind_label,
                   self.name_label, self.status_label, self.rename_button]

        def enter(_event=None):
            if self.on_click is None:
                return
            for widget in widgets:
                widget.configure(bg=BG_CARD_HOVER)
            self.ring.set_background(BG_CARD_HOVER)

        def leave(_event=None):
            for widget in widgets:
                widget.configure(bg=BG_CARD)
            self.ring.set_background(BG_CARD)

        for widget in widgets:
            widget.bind("<Enter>", enter)
            widget.bind("<Leave>", leave)

    # ------------------------------------------------------------------
    # Renaming
    # ------------------------------------------------------------------

    def _start_rename(self, _event=None) -> None:
        """Opens the inline editor for the device name."""
        if self.on_rename is None or self._editor is not None:
            return

        self.name_label.grid_remove()

        row = tk.Frame(self._body, bg=BG_CARD)
        row.grid(row=1, column=1, sticky="ew")
        row.grid_columnconfigure(0, weight=1)

        entry = tk.Entry(row, bg="#101113", fg=FG, insertbackground=ACCENT,
                         relief="flat", bd=0,
                         font=(self.family, scale_font(10, self.dpi)))
        entry.grid(row=0, column=0, sticky="ew",
                   padx=(0, scale_pixels(8, self.dpi)))
        entry.insert(0, self.name_label.cget("text"))
        entry.select_range(0, "end")

        def commit(_event=None):
            self._finish_rename(entry.get())

        def cancel(_event=None):
            self._cancel_rename()

        entry.bind("<Return>", commit)
        entry.bind("<Escape>", cancel)
        entry.bind("<FocusOut>", commit)

        self._editor = entry
        self._editor_row = row
        entry.focus_set()

    def _finish_rename(self, text: str) -> None:
        """Applies the new name and closes the editor."""
        entry = self._editor
        self._editor = None
        if entry is not None:
            entry.destroy()
        if self._editor_row is not None:
            self._editor_row.destroy()
            self._editor_row = None
        self.name_label.grid()

        name = text.strip()
        if name and name != self.name_label.cget("text"):
            # Show the new name right away; the app stores it and refreshes
            # the whole list afterwards.
            self.name_label.configure(text=name)

        if self.on_rename is not None:
            self.on_rename(self._original_name, name)

    def _cancel_rename(self) -> None:
        """Closes the editor without changing the name."""
        entry = self._editor
        self._editor = None
        if entry is not None:
            entry.destroy()
        if self._editor_row is not None:
            self._editor_row.destroy()
            self._editor_row = None
        self.name_label.grid()

    def update(self, device) -> None:
        """Refreshes the card with a new reading."""
        self._percent = device.percent
        self._charging = device.charging
        self._original_name = getattr(device, "original_name", device.name)

        self.kind_label.configure(text=KIND_ICONS.get(device.kind, "DEVICE"))
        self.name_label.configure(text=device.name)
        self.ring.set_percent(device.percent, device.charging)

        if device.charging:
            text, fg = "充电中", CHARGING
        elif device.percent is None:
            text, fg = "未连接", FG_MUTED
        else:
            text, fg = device.subtitle, FG_DIM
        self.status_label.configure(text=text, fg=fg)

    def set_details(self, rows: list[tuple[str, str]]) -> None:
        """Shows the detail rows under the card."""
        for widget in self._detail_widgets:
            widget.destroy()
        self._detail_widgets.clear()

        if not rows:
            return

        # A thin divider separates the summary from the detail rows.
        divider = tk.Frame(self, bg="#2E3035", height=1)
        divider.pack(fill="x", padx=scale_pixels(16, self.dpi),
                     pady=(0, scale_pixels(8, self.dpi)))
        self._detail_widgets.append(divider)

        label_font = (self.family, scale_font(8, self.dpi))
        gap = scale_pixels(18, self.dpi)
        for key, value in rows:
            row = tk.Frame(self, bg=BG_CARD)
            row.pack(fill="x", padx=(scale_pixels(16, self.dpi), gap),
                     pady=scale_pixels(1, self.dpi))
            tk.Label(row, text=key, bg=BG_CARD, fg=FG_MUTED,
                     font=label_font, anchor="w").pack(side="left")
            tk.Label(row, text=value, bg=BG_CARD, fg=FG,
                     font=label_font, anchor="w").pack(side="right")
            self._detail_widgets.append(row)


class BatteryWindow(tk.Tk):
    """The main window: a header, the device cards and a footer."""

    def __init__(self, app):
        # The process has to be DPI aware before the Tk root window exists.
        self.dpi = set_dpi_aware()

        super().__init__()
        self.app = app
        self.family = pick_font_family(self)
        # Work posted from other threads waits here until the Tk main loop
        # picks it up; Tkinter itself is not thread safe.
        self._pending: queue.Queue = queue.Queue()

        self.title("BatteryTray")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.geometry(f"{scale_pixels(440, self.dpi)}x"
                      f"{scale_pixels(420, self.dpi)}")

        self._cards: list[DeviceCard] = []
        self._build()
        self._drain_pending()

        # The popup that the tray icon shows; it lives on top of the window.
        from .quickpanel import QuickPanel

        self.quick_panel = QuickPanel(self, on_rename=self._ask_rename)

        # Closing the window hides it; the tray icon keeps the app alive.
        self.protocol("WM_DELETE_WINDOW", self.withdraw)

    def post(self, func, *args) -> None:
        """Schedules a call to run on the tkinter thread."""
        self._pending.put((func, args))

    def _drain_pending(self) -> None:
        """Runs the queued calls and schedules the next drain."""
        while True:
            try:
                func, args = self._pending.get_nowait()
            except queue.Empty:
                break
            try:
                func(*args)
            except Exception:
                # A failed UI update must not stop the main loop.
                pass
        self.after(50, self._drain_pending)

    def _build(self) -> None:
        """Builds the window layout."""
        dpi = self.dpi
        s = lambda px: scale_pixels(px, dpi)  # noqa: E731
        f = lambda pt: scale_font(pt, dpi)    # noqa: E731

        # ---- Header ----
        header = tk.Frame(self, bg=BG_HEADER, height=s(78))
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        brand = tk.Frame(header, bg=BG_HEADER)
        brand.pack(side="left", padx=s(20), pady=s(15))
        tk.Label(brand, text="BATTERYTRAY", bg=BG_HEADER, fg=ACCENT,
                 font=(self.family, f(12), "bold")).pack(anchor="w")
        tk.Label(brand, text="鼠标与耳机电量", bg=BG_HEADER, fg=FG_MUTED,
                 font=(self.family, f(8))).pack(anchor="w", pady=(s(2), 0))

        self.header_status = tk.Label(header, text="", bg=BG_HEADER, fg=FG_DIM,
                                      font=(self.family, f(8)), anchor="e")
        self.header_status.pack(side="right", padx=s(20))

        tk.Frame(self, bg="#232428", height=1).pack(fill="x", side="top")

        # ---- Device list ----
        # The list lives inside a canvas so that many devices can be scrolled
        # instead of being squeezed into an unreadable strip.
        list_wrap = tk.Frame(self, bg=BG)
        list_wrap.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(list_wrap, bg=BG, highlightthickness=0,
                                 bd=0)
        self.scrollbar = tk.Scrollbar(list_wrap, orient="vertical",
                                      command=self.canvas.yview,
                                      width=s(10), troughcolor=BG,
                                      bg="#24262A", activebackground="#3A3D42",
                                      bd=0, highlightthickness=0)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True,
                         padx=(s(16), 0), pady=(s(16), 0))
        self.scrollbar.pack(side="right", fill="y", padx=(0, s(8)),
                            pady=(s(16), 0))
        # The scrollbar is only useful when the content overflows.
        self.scrollbar.pack_forget()

        self.list_frame = tk.Frame(self.canvas, bg=BG)
        self._window_id = self.canvas.create_window((0, 0), window=self.list_frame,
                                                    anchor="nw")

        self.list_frame.bind("<Configure>", self._on_list_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self._bind_mousewheel(self.canvas)
        self._bind_mousewheel(self.list_frame)

        # ---- Footer ----
        tk.Frame(self, bg="#232428", height=1).pack(fill="x", side="bottom")
        footer = tk.Frame(self, bg=BG_FOOTER, height=s(48))
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        self.summary_label = tk.Label(footer, text="", bg=BG_FOOTER, fg=FG_DIM,
                                      font=(self.family, f(8)), anchor="w")
        self.summary_label.pack(side="left", padx=s(20))

        tk.Button(footer, text="设置", command=self._open_settings,
                  bg="#24262A", fg=FG, activebackground="#2E3136",
                  activeforeground=ACCENT, relief="flat", bd=0,
                  font=(self.family, f(8)), padx=s(16), pady=s(5),
                  highlightthickness=0, cursor="hand2").pack(side="right",
                                                             padx=(0, s(10)), pady=s(8))

        tk.Button(footer, text="刷新", command=self.app.request_refresh,
                  bg="#24262A", fg=FG, activebackground="#2E3136",
                  activeforeground=ACCENT, relief="flat", bd=0,
                  font=(self.family, f(8)), padx=s(16), pady=s(5),
                  highlightthickness=0, cursor="hand2").pack(side="right",
                                                             padx=s(20), pady=s(8))

    def _open_settings(self) -> None:
        """Shows the settings dialog and applies the result."""
        self.open_settings()

    def _on_list_configure(self, _event=None) -> None:
        """Keeps the canvas wide enough for the list frame."""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        """Keeps the list frame as wide as the canvas."""
        self.canvas.itemconfigure(self._window_id, width=event.width)

    def _bind_mousewheel(self, widget: tk.Widget) -> None:
        """Scrolls the list with the mouse wheel."""
        def on_wheel(event):
            # Only scroll when there is something to scroll.
            if self.canvas.bbox("all") is None:
                return
            top = self.canvas.yview()[0]
            bottom = self.canvas.yview()[1]
            if top <= 0 and bottom >= 1:
                return
            if event.delta < 0:
                self.canvas.yview_scroll(-2, "units")
            else:
                self.canvas.yview_scroll(2, "units")

        widget.bind("<MouseWheel>", on_wheel)
        widget.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-2, "units"))
        widget.bind("<Button-5>", lambda e: self.canvas.yview_scroll(2, "units"))

    def set_devices(self, devices: list) -> None:
        """Rebuilds the device cards."""
        # Every child has to go; destroying only the cards would leave the
        # placeholder label behind and the list would grow on every refresh.
        for child in self.list_frame.winfo_children():
            child.destroy()
        self._cards.clear()

        # The popup shows the same readings.
        self.quick_panel.set_devices(devices)

        if not devices:
            tk.Label(self.list_frame, text="未检测到设备", bg=BG, fg=FG_MUTED,
                     font=(self.family, scale_font(10, self.dpi))).pack(
                         pady=scale_pixels(40, self.dpi))
            self.summary_label.configure(text="")
            self.header_status.configure(text="")
            self._update_scrollbar()
            return

        lowest = min((d.percent for d in devices if d.percent is not None),
                     default=None)
        charging = any(d.charging for d in devices)
        if lowest is None:
            self.header_status.configure(text="等待设备响应", fg=FG_MUTED)
        elif charging:
            self.header_status.configure(text=f"正在充电 · 最低 {lowest}%",
                                         fg=CHARGING)
        elif lowest < MEDIUM:
            self.header_status.configure(text=f"电量偏低 · {lowest}%", fg=DANGER)
        else:
            self.header_status.configure(text=f"全部正常 · 最低 {lowest}%",
                                         fg=ACCENT)

        for device in devices:
            card = DeviceCard(self.list_frame, self.family, self.dpi,
                              on_rename=self._rename_device)
            card.update(device)
            card.pack(fill="x", pady=(0, scale_pixels(10, self.dpi)))
            card.set_details(device.detail_rows)
            self._cards.append(card)

        connected = sum(1 for d in devices if d.percent is not None)
        self.summary_label.configure(
            text=f"{len(devices)} 个设备 · {connected} 个已连接")

        self.list_frame.update_idletasks()
        self._update_scrollbar()
        self.resize_to_content()

    def _rename_device(self, original_name: str, new_name: str) -> None:
        """Stores a new name for a device and refreshes the view."""
        if self.app is None:
            return
        self.app.rename_device(original_name, new_name)

    def _ask_rename(self, original_name: str) -> None:
        """Opens the rename dialog for a device.

        Used by the quick popup, which has no room for an inline editor.
        """
        from .renamedialog import ask_rename

        current = original_name
        for card in self._cards:
            if card._original_name == original_name:
                current = card.name_label.cget("text")
                break
        else:
            for row in self.quick_panel._rows:
                if row._original_name == original_name:
                    current = row.name_label.cget("text")
                    break

        new_name = ask_rename(self, self.family, self.dpi,
                              original_name, current)
        if new_name is None:
            return
        self._rename_device(original_name, new_name)

    def toggle_panel(self) -> None:
        """Shows or hides the popup with the battery levels."""
        self.quick_panel.toggle()

    def open_settings(self) -> None:
        """Shows the settings window."""
        from .settingsdialog import ask_settings

        config = getattr(self.app, "config", None)
        if config is None:
            return

        new_config = ask_settings(self, config, self.family, self.dpi)
        if new_config is None:
            return

        self.app.apply_config(new_config)

    def _update_scrollbar(self) -> None:
        """Shows the scrollbar only when the content does not fit."""
        bbox = self.canvas.bbox("all")
        if bbox is None:
            self.scrollbar.pack_forget()
            return
        content_height = bbox[3] - bbox[1]
        if content_height > self.canvas.winfo_height():
            self.scrollbar.pack(side="right", fill="y", padx=(0, scale_pixels(8, self.dpi)),
                                pady=(scale_pixels(16, self.dpi), 0))
        else:
            self.scrollbar.pack_forget()

    def show(self) -> None:
        """Brings the window to the front."""
        self.deiconify()
        self.lift()
        self.focus_force()

    def toggle(self) -> None:
        """Shows the window, or hides it when it is already visible."""
        if self.winfo_viewable():
            self.withdraw()
        else:
            self.show()

    def resize_to_content(self) -> None:
        """Sizes the window so every device card fits without scrolling."""
        self.update_idletasks()
        bbox = self.canvas.bbox("all")
        if bbox is None:
            return
        content_height = bbox[3] - bbox[1]
        # The canvas starts below the header; the footer is packed at the
        # bottom, so the window has to be tall enough for both.
        wanted = content_height + scale_pixels(16, self.dpi) \
            + scale_pixels(78, self.dpi) + scale_pixels(49, self.dpi)
        current = self.winfo_height()
        # Grow to fit, but never shrink below what is already shown.
        if wanted > current:
            self.geometry(f"{self.winfo_width()}x{wanted}")
            self.update_idletasks()
