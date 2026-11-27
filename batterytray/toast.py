"""The card that tells the user a device is low on charge.

Windows shows a grey balloon with the name of the process and an English
sentence in it. This card carries the same information in the look of the
main window: the dark card, the small battery with the number inside it and
the device name.

It appears above the notification area, stays for a few seconds and goes
away by itself. Clicking it opens the window, so the user can see the other
devices as well.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import tkinter as tk
from tkinter import font as tkfont

from PIL import ImageTk

from .art import battery_icon_image
from .dpi import scale_pixels
from .dwm import apply_rounded_corners, frame_handle, hide_window_border
from .widgets import BG_BORDER, BG_CARD, DANGER, FG, FG_MUTED

# The card has the size of a row of the main window with a little more
# room around the text.
CARD_WIDTH = 352
CARD_HEIGHT = 72
ICON_WIDTH = 50
ICON_HEIGHT = 25
NAME_X = 16 + ICON_WIDTH + 14

# How long the card stays and how it comes and goes.
VISIBLE_MS = 7000
FADE_STEPS = 10
FADE_MS = 18

SPI_GETWORKAREA = 0x0030


class LowBatteryToast(tk.Toplevel):
    """A small card that says one device is low on charge."""

    def __init__(self, master: tk.Misc, on_open=None):
        super().__init__(master)

        self.dpi = getattr(master, "dpi", 96.0)
        self.family = getattr(master, "family", "Segoe UI")
        self.on_open = on_open

        self._life = None
        self._fade = None
        self._round = []
        self._closing = False

        self.overrideredirect(True)
        self.configure(bg=BG_BORDER)
        self.title("BatteryTray 电量提醒")
        self.withdraw()
        self.attributes("-alpha", 0.0)

        self._width = scale_pixels(CARD_WIDTH, self.dpi)
        self._height = scale_pixels(CARD_HEIGHT, self.dpi)
        self.geometry(f"{self._width}x{self._height}")

        # The window itself is the border, the canvas inside is the card.
        # The corners are rounded by Windows, like the popup of the tray.
        self.canvas = tk.Canvas(self, bg=BG_CARD, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True, padx=1, pady=1)
        # One binding on the window is enough: the events of a child
        # travel up to the window, and binding both would open it twice.
        self.bind("<Button-1>", self._open)

        self._name_font = (self.family, -scale_pixels(13, self.dpi), "bold")
        self._status_font = (self.family, -scale_pixels(10, self.dpi))
        self._icon_photo = None
        self._icon_key = None

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------

    def show(self, name: str, percent: int | None) -> None:
        """Fills the card and shows it above the notification area."""
        self._closing = False
        self._draw(name, percent)
        self._place()
        self.deiconify()
        self.lift()
        # A notification has to be seen, but only while it is there. The
        # window is dropped before it is destroyed.
        self.attributes("-topmost", True)
        self._round_corners()
        self._fade_in()
        self._restart_life()

    def _draw(self, name: str, percent: int | None) -> None:
        s = lambda px: scale_pixels(px, self.dpi)  # noqa: E731
        self.canvas.delete("all")

        height = self._height - s(2)
        value = "--" if percent is None else f"{percent}%"
        icon_w = s(ICON_WIDTH)
        icon_h = s(ICON_HEIGHT)
        key = (icon_w, icon_h, percent, value)
        if key != self._icon_key:
            self._icon_photo = ImageTk.PhotoImage(
                battery_icon_image(icon_w, icon_h, percent, False, False,
                                   text=value))
            self._icon_key = key
        self.canvas.create_image(s(16), (height - icon_h) // 2, anchor="nw",
                                 image=self._icon_photo)

        room = self._width - s(NAME_X) - s(16)
        self.canvas.create_text(
            s(NAME_X), s(15), text=self._fit(name, self._name_font, room),
            anchor="nw", fill=FG, font=self._name_font)

        if percent is None:
            status = "电量不足"
        else:
            status = f"电量低，只剩 {percent}%"
        self.canvas.create_text(
            s(NAME_X), s(38),
            text=self._fit(status, self._status_font, room),
            anchor="nw", fill=DANGER, font=self._status_font)

        # The chevron says the card opens the window, the same way the
        # cards of the main window show that they are clickable.
        self.canvas.create_text(
            self._width - s(16), height / 2, text="\u203a", anchor="e",
            fill=FG_MUTED,
            font=(self.family, -scale_pixels(17, self.dpi)))

    def _fit(self, text: str, font, room: int) -> str:
        """Shortens a text until it fits into the room of the card."""
        measure = tkfont.Font(root=self.canvas, font=font)
        if measure.measure(text) <= room:
            return text
        shortened = text
        while shortened and measure.measure(shortened + "…") > room:
            shortened = shortened[:-1]
        return (shortened + "…") if shortened else "…"

    # ------------------------------------------------------------------
    # Showing and hiding
    # ------------------------------------------------------------------

    def _place(self) -> None:
        """Puts the card above the notification area of the taskbar."""
        rect = wt.RECT()
        try:
            asked = ctypes.windll.user32.SystemParametersInfoW(
                SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
        except Exception:
            asked = 0
        if asked and rect.right > rect.left and rect.bottom > rect.top:
            right, bottom = rect.right, rect.bottom
        else:
            right = self.winfo_screenwidth()
            bottom = self.winfo_screenheight()

        margin = scale_pixels(18, self.dpi)
        x = max(0, right - self._width - margin)
        y = max(0, bottom - self._height - margin)
        self.geometry(f"+{x}+{y}")

    def _round_corners(self) -> None:
        def apply():
            hwnd = frame_handle(self)
            if hwnd:
                apply_rounded_corners(hwnd)
                hide_window_border(hwnd)

        # The calls are kept, so they can be cancelled when the card is
        # destroyed before they ran.
        self._cancel_round()
        self._round = [self.after_idle(apply), self.after(120, apply)]

    def _cancel_round(self) -> None:
        for event in self._round:
            try:
                self.after_cancel(event)
            except tk.TclError:
                pass
        self._round = []

    def _restart_life(self) -> None:
        self._cancel_life()
        self._life = self.after(VISIBLE_MS, self.close)

    def _cancel_life(self) -> None:
        if self._life is not None:
            try:
                self.after_cancel(self._life)
            except tk.TclError:
                pass
            self._life = None

    def _cancel_fade(self) -> None:
        if self._fade is not None:
            try:
                self.after_cancel(self._fade)
            except tk.TclError:
                pass
            self._fade = None

    def _fade_in(self) -> None:
        self._cancel_fade()

        def step(index: int = 1) -> None:
            self._fade = None
            try:
                self.attributes("-alpha", index / FADE_STEPS)
            except tk.TclError:
                return
            if index < FADE_STEPS:
                self._fade = self.after(FADE_MS, lambda: step(index + 1))

        step()

    def close(self) -> None:
        """Fades the card out and destroys it."""
        if self._closing:
            return
        self._closing = True
        self._cancel_life()
        self._cancel_fade()

        def step(index: int = FADE_STEPS) -> None:
            self._fade = None
            index -= 1
            try:
                self.attributes("-alpha", max(0.0, index / FADE_STEPS))
            except tk.TclError:
                self._destroy()
                return
            if index > 0:
                self._fade = self.after(FADE_MS, lambda: step(index))
            else:
                self._destroy()

        step()

    def _destroy(self) -> None:
        self._cancel_life()
        self._cancel_fade()
        self._cancel_round()
        try:
            self.attributes("-topmost", False)
        except tk.TclError:
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass

    def _open(self, _event=None) -> None:
        """Opens the window, so the user can see every device."""
        self.close()
        if self.on_open is not None:
            self.on_open()
