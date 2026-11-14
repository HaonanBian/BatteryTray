"""The compact battery row of the main window.

Each device is one short row: a small battery with the percentage printed
inside it, followed by the device name. The battery is deliberately the
same size as the text, so it reads as an icon instead of a poster.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

from PIL import ImageTk

from .art import battery_icon_image
from .dpi import scale_pixels
from .widgets import (
    BG,
    BG_BORDER,
    BG_CARD,
    BG_CARD_HOVER,
    BG_FIELD,
    CHARGING,
    FG,
    FG_DIM,
    FG_MUTED,
    draw_rounded_rect,
)

CARD_HEIGHT = 74
ICON_WIDTH = 50
ICON_HEIGHT = 25

# The icon carries its own number, so the name can start right after it.
NAME_X = 16 + ICON_WIDTH + 14


class DeviceCard(tk.Canvas):
    """One device: a small battery, the charge and the name."""

    def __init__(self, master: tk.Misc, family: str, dpi: float = 96.0,
                 on_click=None, on_rename=None, on_configure=None):
        self.dpi = dpi
        s = lambda px: scale_pixels(px, dpi)  # noqa: E731
        super().__init__(master, bg=BG, highlightthickness=0, bd=0,
                         height=s(CARD_HEIGHT))
        self.family = family
        self.on_click = on_click
        self.on_rename = on_rename
        self.on_configure = on_configure

        self._percent: int | None = None
        self._charging = False
        self._connected = True
        self._kind = "device"
        self._original_name = ""
        self._full_name = ""
        self._detail_rows: list[tuple[str, str]] = []
        self._hover = False
        self._product_id: int | None = None
        self._has_config = False
        self._width = 0
        self._editor: tk.Entry | None = None
        self._editor_window: int | None = None
        self._icon_photo = None
        self._icon_key = None

        self._name_font = (family, -s(13), "bold")
        self._status_font = (family, -s(10))
        self._detail_font = (family, -s(9))
        self._icon_font = ("Segoe MDL2 Assets", -s(13))

        self.name_label = tk.Label(self, text="", bg=BG_CARD, fg=FG,
                                   font=self._name_font, anchor="w")
        self._name_window = self.create_window(0, 0, anchor="nw",
                                               window=self.name_label)

        self.status_label = tk.Label(self, text="", bg=BG_CARD, fg=FG_DIM,
                                     font=self._status_font, anchor="w")
        self._status_window = self.create_window(0, 0, anchor="nw",
                                                 window=self.status_label)

        self.bind("<Configure>", self._on_configure)
        for widget in (self, self.name_label, self.status_label):
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)

        self._draw()
        self._clip_name()

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def _height(self) -> int:
        return scale_pixels(CARD_HEIGHT, self.dpi)

    def _name_x(self) -> int:
        return scale_pixels(NAME_X, self.dpi)

    def _right_icons(self) -> tuple[int, int]:
        width = max(self.winfo_width(), 1)
        edit = width - scale_pixels(20, self.dpi)
        gear = edit - scale_pixels(24, self.dpi)
        return gear, edit

    def _on_configure(self, event=None) -> None:
        width = self.winfo_width()
        if width <= 1 or width == self._width:
            return
        self._width = width
        self._draw()
        self._clip_name()

    def refresh_layout(self) -> None:
        """Redraws after the grid has given the card its real width.

        A look at the name is not guaranteed from a ``<Configure>`` event
        that is still queued, so the window calls this once after placing
        the cards.
        """
        self._width = self.winfo_width()
        self._draw()
        self._clip_name()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def _draw(self) -> None:
        self.delete("deco")
        width = self.winfo_width()
        if width <= 1:
            return

        s = lambda px: scale_pixels(px, self.dpi)  # noqa: E731
        height = self._height()
        fill = BG_CARD_HOVER if self._hover else BG_CARD
        self.name_label.configure(bg=fill)
        self.status_label.configure(bg=fill)

        draw_rounded_rect(self, 0, 0, width, height, s(13), fill=fill,
                          outline=BG_BORDER, width=1, tags="deco")

        # ---- The battery icon, with the number inside it ----
        value = "--" if self._percent is None else f"{self._percent}%"
        icon_w = s(ICON_WIDTH)
        icon_h = s(ICON_HEIGHT)
        key = (icon_w, icon_h, self._percent, self._charging, self._hover,
               value)
        if key != self._icon_key:
            self._icon_photo = ImageTk.PhotoImage(
                battery_icon_image(icon_w, icon_h, self._percent,
                                   self._charging, self._hover, text=value))
            self._icon_key = key
        self.create_image(s(16), (height - icon_h) // 2, anchor="nw",
                          image=self._icon_photo, tags="deco")

        # ---- The name and the status ----
        name_x = self._name_x()
        self.coords(self._name_window, name_x, s(9))
        self.coords(self._status_window, name_x, s(35))

        # ---- The buttons on the right ----
        gear, edit = self._right_icons()
        icon_y = height / 2
        if self._has_config:
            self.create_text(gear, icon_y, text="\ue713", fill=FG_MUTED,
                             font=self._icon_font, tags=("deco", "icon_config"))
            self.tag_bind("icon_config", "<Button-1>",
                          lambda _event: self._open_configure())
        self.create_text(edit, icon_y, text="\ue70f", fill=FG_MUTED,
                         font=self._icon_font, tags=("deco", "icon_rename"))
        self.tag_bind("icon_rename", "<Button-1>",
                      lambda _event: self._start_rename())

        # ---- The compact details at the right of the status line ----
        details = self._detail_text()
        if details:
            measure = tkfont.Font(root=self, font=self._detail_font)
            detail_w = measure.measure(details)
            status_w = self.status_label.winfo_reqwidth()
            room = width - name_x - s(64)
            if status_w + detail_w + s(16) <= room:
                self.create_text(width - s(64), s(44), text=details,
                                 anchor="e", fill=FG_MUTED,
                                 font=self._detail_font, tags="deco")

    def _detail_text(self) -> str:
        parts: list[str] = []
        for key, value in self._detail_rows:
            if key == "刷新率":
                parts.append(value)
            elif key == "DPI":
                parts.append(f"{value} DPI")
        return " · ".join(parts)

    # ------------------------------------------------------------------
    # Hover
    # ------------------------------------------------------------------

    def _on_enter(self, _event=None) -> None:
        if self._hover:
            return
        self._hover = True
        self._draw()

    def _on_leave(self, _event=None) -> None:
        if not self._hover:
            return
        self._hover = False
        self._draw()

    # ------------------------------------------------------------------
    # The buttons
    # ------------------------------------------------------------------

    def _open_configure(self, _event=None) -> None:
        if self.on_configure is None:
            return
        self.on_configure(self._original_name,
                          self._full_name or self.name_label.cget("text"),
                          getattr(self, "_product_id", None))

    def _start_rename(self, _event=None) -> None:
        if self.on_rename is None or self._editor is not None:
            return

        s = lambda px: scale_pixels(px, self.dpi)  # noqa: E731
        width = self.winfo_width() - self._name_x() - s(66)
        width = max(s(80), width)
        entry = tk.Entry(self, bg=BG_FIELD, fg=FG, insertbackground=FG,
                         relief="flat", bd=0, highlightthickness=1,
                         highlightbackground="#3A424A",
                         highlightcolor="#8FB9A0",
                         font=self._name_font)
        window = self.create_window(self._name_x(), s(7), anchor="nw",
                                    width=width, height=s(22), window=entry)
        self.itemconfigure(self._name_window, state="hidden")
        entry.insert(0, self._full_name or self.name_label.cget("text"))
        entry.select_range(0, "end")

        def commit(_event=None):
            if self._editor is not entry:
                return
            self._finish_rename(entry.get())

        def cancel(_event=None):
            if self._editor is not entry:
                return
            self._cancel_rename()

        entry.bind("<Return>", commit)
        entry.bind("<Escape>", cancel)
        entry.bind("<FocusOut>", commit)
        self._editor = entry
        self._editor_window = window
        entry.focus_set()

    def _finish_rename(self, text: str) -> None:
        self._destroy_editor()
        name = text.strip()
        if name and name != self._full_name:
            self._full_name = name
            self.name_label.configure(text=name)
            self._clip_name()
        if self.on_rename is not None:
            self.on_rename(self._original_name, name)

    def _cancel_rename(self) -> None:
        self._destroy_editor()
        self._clip_name()

    def _destroy_editor(self) -> None:
        entry = self._editor
        self._editor = None
        if self._editor_window is not None:
            try:
                self.delete(self._editor_window)
            except Exception:
                pass
            self._editor_window = None
        if entry is not None:
            entry.destroy()
        self.itemconfigure(self._name_window, state="normal")

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------

    def update(self, device) -> None:
        self._percent = device.percent
        self._charging = device.charging
        self._connected = getattr(device, "connected", True)
        self._original_name = getattr(device, "original_name", device.name)
        self._product_id = getattr(device, "product_id", None)
        self._kind = getattr(device, "kind", "device")
        self._has_config = self._kind == "mouse" and self.on_configure is not None

        self._full_name = device.name
        self.name_label.configure(text=device.name)
        self._detail_rows = list(getattr(device, "detail_rows", []))

        if device.charging:
            text, fg = "充电中", CHARGING
        elif not self._connected or device.percent is None:
            text, fg = "未连接", FG_MUTED
        else:
            text, fg = device.subtitle, FG_DIM
        self.status_label.configure(text=text, fg=fg)

        self._icon_key = None
        self._draw()
        self._clip_name()

    def set_details(self, rows: list[tuple[str, str]]) -> None:
        self._detail_rows = list(rows)
        self._draw()

    def _clip_name(self) -> None:
        if not self._full_name:
            return
        width = self.winfo_width()
        if width <= 1:
            return
        room = width - self._name_x() - scale_pixels(66, self.dpi)
        if room < scale_pixels(40, self.dpi):
            return
        measure = tkfont.Font(root=self, font=self._name_font)
        if measure.measure(self._full_name) <= room:
            if self.name_label.cget("text") != self._full_name:
                self.name_label.configure(text=self._full_name)
            return
        for length in range(len(self._full_name) - 1, 0, -1):
            candidate = self._full_name[:length] + "…"
            if measure.measure(candidate) <= room:
                self.name_label.configure(text=candidate)
                return
        self.name_label.configure(text="…")
