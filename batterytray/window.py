"""The main window: a dark dashboard of large battery cards.

The window shows one card per device. Every card is a wide battery with
its charge painted as a muted glass fill and the percentage in white; the
device name and its connection details sit above and below the battery.
"""

from __future__ import annotations

import queue
import tkinter as tk
from tkinter import font as tkfont

from .card import DeviceCard
from .dpi import scale_pixels, set_dpi_aware
from .dwm import style_window
from .widgets import (
    ACCENT,
    BG,
    BG_DIVIDER,
    CHARGING,
    DANGER,
    FG,
    FG_DIM,
    FG_MUTED,
    GlassButton,
)

# The level at which the colour of the status changes.
MEDIUM = 20

# The most device cards that fit next to each other in one row.
MAX_COLUMNS = 4


def pick_font_family(root: tk.Misc) -> str:
    """Chooses the best UI font available on this system."""
    available = set(tkfont.families(root))
    for name in ("Microsoft YaHei UI", "Segoe UI", "Tahoma"):
        if name in available:
            return name
    return "TkDefaultFont"


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
        # The window can be resized freely. The minimum keeps the header
        # and the footer readable, the canvas scrolls whatever does not
        # fit.
        self.resizable(True, True)
        self.minsize(scale_pixels(360, self.dpi),
                     scale_pixels(260, self.dpi))
        self.geometry(f"{scale_pixels(440, self.dpi)}x"
                      f"{scale_pixels(300, self.dpi)}")

        self._cards: list[DeviceCard] = []
        # How many cards fit next to each other. One until the window is
        # wide enough for two.
        self._columns = 1
        # Set while a relayout is waiting for the event loop, so it is
        # not started twice.
        self._relayout_pending = False
        # Set once the user resizes the window by hand. From then on the
        # window keeps the size they picked and the list scrolls.
        self._user_resized = False
        # The size the window had the last time it was laid out. A change
        # means the user resized it, which is what sets the flag above.
        self._last_size: tuple[int, int] | None = None
        # Set while the code itself changes the size, so the resize is not
        # mistaken for the user reaching for the border.
        self._resizing = False
        self._build()
        self._drain_pending()

        # The popup that the tray icon shows; it lives on top of the window.
        from .quickpanel import QuickPanel

        self.quick_panel = QuickPanel(self, on_rename=self._ask_rename,
                                      on_open=self._open_main_from_panel)

        # Closing the window hides it; the tray icon keeps the app alive.
        self.protocol("WM_DELETE_WINDOW", self.withdraw)

        # Remember that the user picked a size, so the window stops
        # growing on its own when new devices show up.
        self.bind("<Configure>", self._on_window_configure)

        # The title bar of Windows is white and does not fit to the dark
        # window. Windows 11 can give the window a translucent backdrop,
        # which makes the title bar part of the window.
        style_window(self)

    def _on_window_configure(self, event) -> None:
        """Notices that the user resized the window.

        The first layout does not count, because the window has not been
        shown yet and its size still comes from the code. Neither does a
        resize that the code asked for itself.
        """
        if event.widget is not self:
            return
        size = (self.winfo_width(), self.winfo_height())
        if self._last_size is None:
            self._last_size = size
            return
        if size == self._last_size:
            return
        self._last_size = size
        if not self._resizing:
            self._user_resized = True

    def forget_user_resize(self) -> None:
        """Starts tracking the window size again.

        The window stops growing on its own after the user has resized
        it. This undoes that, so the window fits its content again.
        """
        self._user_resized = False
        self._last_size = (self.winfo_width(), self.winfo_height())

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
        fp = lambda px: -scale_pixels(px, dpi)  # noqa: E731

        # ---- Header ----
        header = tk.Frame(self, bg=BG, height=s(58))
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        brand = tk.Frame(header, bg=BG)
        brand.pack(side="left", padx=s(18), pady=s(9))
        tk.Label(brand, text="BatteryTray", bg=BG, fg=FG,
                 font=(self.family, fp(15), "bold")).pack(anchor="w")
        tk.Label(brand, text="鼠标与耳机电量", bg=BG, fg=FG_MUTED,
                 font=(self.family, fp(9))).pack(anchor="w", pady=(s(1), 0))

        self.header_status = tk.Label(header, text="", bg=BG, fg=FG_DIM,
                                      font=(self.family, fp(9)), anchor="e")
        self.header_status.pack(side="right", padx=s(18))

        tk.Frame(self, bg=BG_DIVIDER, height=1).pack(fill="x", side="top")

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

        # The scroll bar gets its own column, so the canvas takes the rest
        # of the room. The canvas may not claim the room of the scroll
        # bar, otherwise the scroll bar ends up outside of the window when
        # the window becomes small.
        list_wrap.grid_columnconfigure(0, weight=1)
        list_wrap.grid_columnconfigure(1, weight=0, minsize=0)
        list_wrap.grid_rowconfigure(0, weight=1)

        self.canvas.grid(row=0, column=0, sticky="nsew",
                         padx=(s(14), s(8)), pady=(s(12), 0))
        self.scrollbar.grid(row=0, column=1, sticky="ns",
                            padx=(0, s(6)), pady=(s(12), 0))
        # The scrollbar is only useful when the content overflows.
        self.scrollbar.grid_remove()

        self.list_frame = tk.Frame(self.canvas, bg=BG)
        self._window_id = self.canvas.create_window((0, 0), window=self.list_frame,
                                                    anchor="nw")

        self.list_frame.bind("<Configure>", self._on_list_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # The wheel is bound to the whole window, because the cards are
        # children of the list and a binding on the list alone would not
        # see the wheel while the pointer rests on a card.
        self.bind("<MouseWheel>", self._on_mousewheel)
        self.bind("<Button-4>", self._on_mousewheel)
        self.bind("<Button-5>", self._on_mousewheel)

        # ---- Footer ----
        tk.Frame(self, bg=BG_DIVIDER, height=1).pack(fill="x", side="bottom")
        footer = tk.Frame(self, bg=BG, height=s(42))
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        self.summary_label = tk.Label(footer, text="", bg=BG, fg=FG_DIM,
                                      font=(self.family, fp(9)), anchor="w")
        self.summary_label.pack(side="left", padx=s(18))

        GlassButton(footer, "设置", self.family, dpi,
                    command=self._open_settings,
                    background=BG).pack(side="right", padx=(0, s(10)),
                                        pady=s(6))

        GlassButton(footer, "刷新", self.family, dpi,
                    command=self.app.request_refresh,
                    background=BG).pack(side="right", padx=(0, s(18)),
                                        pady=s(6))

    def _open_settings(self) -> None:
        """Shows the settings dialog and applies the result."""
        self.open_settings()

    def _on_list_configure(self, _event=None) -> None:
        """Keeps the canvas wide enough for the list frame."""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        """Keeps the list frame as wide as the canvas.

        The width decides whether the cards fit in one column or in two,
        so the layout has to be redone whenever it changes. The scroll
        bar is placed again as well, because it has to move when the
        window becomes smaller.
        """
        self.canvas.itemconfigure(self._window_id, width=event.width)
        self._update_scrollbar()
        if not self._cards:
            return
        if self._column_count() == self._columns:
            return
        # The cards cannot be moved while Tk is in the middle of the
        # layout, so the work is put off until the event is over.
        if self._relayout_pending:
            return
        self._relayout_pending = True
        self.after_idle(self._relayout_cards)

    def _relayout_cards(self) -> None:
        """Moves the cards to a second column once there is room."""
        self._relayout_pending = False
        if not self._cards:
            return
        self._layout_cards()
        # The scroll bar may be needed now, but the layout must not be
        # asked for again from here: this runs inside the event loop.
        self._update_scrollbar()

    def _on_mousewheel(self, event) -> None:
        """Scrolls the device list with the mouse wheel.

        The binding sits on the window, so it also fires while the pointer
        rests on a card. It only scrolls when the pointer is over the list,
        so the wheel keeps its usual meaning everywhere else.
        """
        if not self._pointer_over_list():
            return

        if getattr(event, "num", None) == 4:
            self.canvas.yview_scroll(-2, "units")
            return
        if getattr(event, "num", None) == 5:
            self.canvas.yview_scroll(2, "units")
            return

        delta = getattr(event, "delta", 0)
        if not delta:
            return

        # Only scroll when there is something to scroll.
        if self.canvas.bbox("all") is None:
            return
        top = self.canvas.yview()[0]
        bottom = self.canvas.yview()[1]
        if top <= 0 and bottom >= 1:
            return

        # A notch of the wheel is 120 units on Windows.
        steps = int(-delta / 120) * 2 or (-2 if delta > 0 else 2)
        self.canvas.yview_scroll(steps, "units")

    def _pointer_over_list(self) -> bool:
        """Whether the pointer is over the list of devices."""
        x = self.winfo_pointerx()
        y = self.winfo_pointery()
        left = self.canvas.winfo_rootx()
        top = self.canvas.winfo_rooty()
        return (left <= x < left + self.canvas.winfo_width()
                and top <= y < top + self.canvas.winfo_height())

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
            # The cards use the grid, so the placeholder has to use it too.
            tk.Label(self.list_frame, text="未检测到设备", bg=BG, fg=FG_MUTED,
                     font=(self.family, -scale_pixels(10, self.dpi))).grid(
                         row=0, column=0, pady=scale_pixels(40, self.dpi))
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
                              on_rename=self._rename_device,
                              on_configure=self._open_mouse_settings)
            card.update(device)
            card.set_details(device.detail_rows)
            self._cards.append(card)

        # The cards have to be placed after the layout, because the width
        # of the list decides whether they fit in one column or in two.
        self.update_idletasks()
        self._layout_cards()
        self.update_idletasks()
        for card in self._cards:
            card.refresh_layout()
        # The canvas may give the cards their final width one idle cycle
        # later; clip the names again then.
        self.after_idle(self._refresh_cards)

        connected = sum(1 for d in devices if d.percent is not None)
        self.summary_label.configure(
            text=f"{len(devices)} 个设备 · {connected} 个已连接")

        self.list_frame.update_idletasks()
        self._update_scrollbar()
        self.resize_to_content()

    def _refresh_cards(self) -> None:
        """Redraws the cards after the pending layout has settled."""
        for card in self._cards:
            try:
                card.refresh_layout()
            except Exception:
                pass

    def _column_count(self) -> int:
        """How many cards fit side by side in the current window width.

        A card needs room for the battery, the device name and the two
        buttons on the right. Anything narrower than that would clip the
        text, so a new column only appears once there is room for the
        whole card.
        """
        # The width of the window is always up to date, while the canvas
        # keeps the width it had during the last layout. The window is
        # used as the source of truth and the space the list does not get
        # is taken off.
        available = self.winfo_width()
        if available <= 1:
            # The window has not been laid out yet.
            return 1
        # The padding around the list and the scroll bar.
        available -= scale_pixels(40, self.dpi)
        # The width one card needs, plus the gap between two columns. A
        # card has to be wide enough for the battery and for a device
        # name, otherwise the name has to be cut short.
        needed = scale_pixels(360, self.dpi) + scale_pixels(12, self.dpi)
        # As many columns as fit, but never more than the limit.
        columns = available // needed
        return max(1, min(MAX_COLUMNS, columns))

    def _layout_cards(self) -> None:
        """Places the cards in as many columns as fit.

        The window is free to be resized, so the cards move to another
        column as soon as there is room for them.
        """
        columns = self._column_count()
        gap = scale_pixels(12, self.dpi)
        self._columns = columns

        # All columns are the same width and fill the window. The size of
        # the columns is set by hand, because the ``uniform`` option would
        # leave the cards hidden when the number of columns changes.
        width = 0
        if columns > 1:
            # The width of the window is always up to date, while the list
            # frame still has the width of the last layout.
            available = self.winfo_width() - scale_pixels(40, self.dpi)
            width = max(1, (available - gap * (columns - 1)) // columns)
        for column in range(MAX_COLUMNS):
            self.list_frame.grid_columnconfigure(
                column, weight=1 if column < columns else 0,
                minsize=width if column < columns else 0)

        for index, card in enumerate(self._cards):
            row = index // columns
            column = index % columns
            # The gap sits between the columns, not at the edge.
            padx = (0, gap) if column < columns - 1 else 0
            # The card is taken out of the grid and put back in, because
            # Tk leaves the cards hidden when the columns change. The
            # cards would keep the place they had in the old layout and
            # stay invisible.
            card.grid_forget()
            card.grid(row=row, column=column, sticky="nsew",
                      padx=padx, pady=(0, gap))

    def _rename_device(self, original_name: str, new_name: str) -> None:
        """Stores a new name for a device and refreshes the view."""
        if self.app is None:
            return
        self.app.rename_device(original_name, new_name)

    def _open_mouse_settings(self, original_name: str, display_name: str,
                             product_id: int | None) -> None:
        """Opens the settings window of a mouse."""
        from .mousesettingsdialog import ask_mouse_settings

        ask_mouse_settings(self, display_name or original_name, product_id,
                           self.family, self.dpi)

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

    def _open_main_from_panel(self) -> None:
        """Closes the tray strip and opens the full window."""
        self.quick_panel.hide()
        self.show()

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
        # The scrollbar is always placed anew. Placing a widget that is
        # already placed does nothing, so it would keep the place it had
        # when the window was wider and end up outside of the window.
        self.scrollbar.grid_remove()
        bbox = self.canvas.bbox("all")
        if bbox is None:
            return
        content_height = bbox[3] - bbox[1]
        if content_height > self.canvas.winfo_height():
            self.scrollbar.grid(row=0, column=1, sticky="ns",
                                padx=(0, scale_pixels(6, self.dpi)),
                                pady=(scale_pixels(12, self.dpi), 0))

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
        """Grows the window so every device card fits without scrolling.

        The user may resize the window freely. Once they have picked a
        size the window keeps it and the list scrolls instead, so the
        window does not jump around while the devices refresh.
        """
        if self._user_resized:
            return
        self.update_idletasks()
        bbox = self.canvas.bbox("all")
        if bbox is None:
            return
        content_height = bbox[3] - bbox[1]
        # The canvas starts below the header; the footer is packed at the
        # bottom, so the window has to be tall enough for both.
        wanted = content_height + scale_pixels(12, self.dpi) \
            + scale_pixels(58, self.dpi) + scale_pixels(43, self.dpi)
        # Do not grow past the screen: a window taller than the desktop
        # would hide its own footer and the taskbar. The list scrolls.
        limit = self.winfo_screenheight() - scale_pixels(90, self.dpi)
        if limit > scale_pixels(260, self.dpi):
            wanted = min(wanted, limit)
        current = self.winfo_height()
        # Grow to fit, but never shrink below what is already shown.
        if wanted > current:
            self._resizing = True
            try:
                self.geometry(f"{self.winfo_width()}x{wanted}")
                self.update_idletasks()
            finally:
                self._resizing = False
            self._last_size = (self.winfo_width(), self.winfo_height())
