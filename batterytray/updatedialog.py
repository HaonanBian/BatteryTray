"""The window that reports the result of an update check.

The window follows the main window: the same dark background, the soft
green accent and the rounded cards, with the same pixel sized text. The
heading carries a round badge with a mark on it, and the window is closed
by the buttons in the footer.

The panel has three states: it is looking for a new release, it found one,
or the check failed. When the update runs, the panel turns into a progress
view that reports how far the download got and restarts the app when it is
done.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
import webbrowser

from . import __version__
from .dialog import prepare_dialog
from .dpi import scale_font, scale_pixels
from .widgets import (
    ACCENT,
    BG,
    BG_BORDER,
    BG_CARD,
    BG_DIVIDER,
    BG_FIELD,
    DANGER,
    FG,
    FG_DIM,
    FG_MUTED,
    WARNING,
    GlassButton,
    draw_rounded_rect,
    rounded_points,
)

# The ink of the marks that are drawn on the badge.
BADGE_INK = "#20252C"

# The colour of the bar that shows the download.
PROGRESS_TRACK = "#161B20"


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
    if mark == "check":
        # A check that is drawn as two strokes.
        canvas.create_line(size * 0.34, middle,
                           size * 0.46, size * 0.62,
                           fill=BADGE_INK, width=max(2, size * 0.09),
                           capstyle="round", joinstyle="round")
        canvas.create_line(size * 0.46, size * 0.62,
                           size * 0.68, size * 0.38,
                           fill=BADGE_INK, width=max(2, size * 0.09),
                           capstyle="round", joinstyle="round")
    elif mark == "bang":
        # A bar with a dot underneath it.
        bar = size * 0.09
        canvas.create_polygon(
            rounded_points(middle - bar / 2, size * 0.28,
                           middle + bar / 2, size * 0.56, bar / 2),
            fill=BADGE_INK, outline="")
        canvas.create_oval(middle - bar / 2, size * 0.64,
                           middle + bar / 2, size * 0.64 + bar,
                           fill=BADGE_INK, outline="")
    else:
        # An arrow that points up, or down when the file is fetched.
        up = mark == "up"
        head = size * 0.22
        stem = size * 0.10
        top = size * 0.30 if up else size * 0.48
        bottom = size * 0.68 if up else size * 0.34
        if up:
            points = [middle, top,
                      middle + head, top + head * 0.8,
                      middle + stem / 2, top + head * 0.8,
                      middle + stem / 2, bottom,
                      middle - stem / 2, bottom,
                      middle - stem / 2, top + head * 0.8,
                      middle - head, top + head * 0.8]
        else:
            points = [middle, bottom,
                      middle + head, bottom - head * 0.8,
                      middle + stem / 2, bottom - head * 0.8,
                      middle + stem / 2, top,
                      middle - stem / 2, top,
                      middle - stem / 2, bottom - head * 0.8,
                      middle - head, bottom - head * 0.8]
        canvas.create_polygon(points, fill=BADGE_INK, outline="")


class _Card(tk.Canvas):
    """A card with rounded corners that holds the content of the panel.

    The content sits in a frame that is embedded in the canvas, the way
    the device cards of the main window are built: the canvas paints the
    shape and the frame keeps the widgets.
    """

    def __init__(self, master: tk.Misc, dpi: float, padding: int = 16,
                 radius: int = 13):
        super().__init__(master, bg=BG, highlightthickness=0, bd=0, height=1)
        self.padding = scale_pixels(padding, dpi)
        self.radius = scale_pixels(radius, dpi)
        self.body = tk.Frame(self, bg=BG_CARD)
        self._window = self.create_window(self.padding, self.padding,
                                          anchor="nw", window=self.body)
        self.bind("<Configure>", self._on_configure)

    def refresh(self) -> None:
        """Sizes the card to the content inside it.

        A window that is embedded in a canvas does not grow on its own when
        the content changes, so the height is asked for again. The height of
        the embedded window is set to zero first, because a window that was
        made taller once keeps that height and would not shrink.
        """
        self.itemconfigure(self._window, height=0)
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


class UpdateDialog(tk.Toplevel):
    """Shows what the update check found."""

    def __init__(self, master: tk.Misc, family: str, dpi: float,
                 on_install=None):
        super().__init__(master)
        self.dpi = dpi
        self.family = family
        self._closed = False
        # The release that was found, if there is one.
        self.release = None
        # The callback that downloads the release and puts it in place.
        self.on_install = on_install

        self.title("BatteryTray 检查更新")
        self.configure(bg=BG)
        self.resizable(False, False)
        prepare_dialog(self, master)

        s = lambda px: scale_pixels(px, dpi)  # noqa: E731
        f = lambda pt: scale_font(pt, dpi)  # noqa: E731
        # The helpers are kept, so the later methods can use them too.
        self._s = s
        self._f = f

        self._build()

        self.protocol("WM_DELETE_WINDOW", self._close)
        # The card does not grow on its own, so it is told how tall its
        # content is before the window is placed.
        self.card.refresh()
        self.update_idletasks()
        self._centre()

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def _build(self) -> None:
        """Builds the heading, the card with the content and the footer."""
        s = self._s
        f = self._f

        # ---- The heading with the round badge ----
        header = tk.Frame(self, bg=BG, height=s(64))
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        self.badge = tk.Canvas(header, bg=BG, highlightthickness=0, bd=0,
                               width=s(40), height=s(40))
        self.badge.pack(side="left", padx=(s(18), 0), pady=s(12))
        _badge(self.badge, s(40), ACCENT, "up")

        heading = tk.Frame(header, bg=BG)
        heading.pack(side="left", padx=(s(12), 0), fill="x", expand=True)

        self.title_label = tk.Label(heading, text="正在检查更新…", bg=BG,
                                    fg=FG, font=(self.family, f(15), "bold"),
                                    anchor="w")
        self.title_label.pack(anchor="w")

        self.message_label = tk.Label(
            heading, text="正在连接 GitHub，请稍候…", bg=BG, fg=FG_MUTED,
            font=(self.family, f(9)), anchor="w", justify="left")
        self.message_label.pack(anchor="w", pady=(s(1), 0))

        tk.Frame(self, bg=BG_DIVIDER, height=1).pack(fill="x", side="top")

        # ---- The card with the content ----
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        self.card = _Card(body, self.dpi)
        # The card is not allowed to grow, because it decides itself how
        # tall it has to be. If it were stretched, it would keep the height
        # of the first layout for ever.
        self.card.pack(fill="x", padx=s(18), pady=s(16))
        inner = self.card.body

        self.version_label = tk.Label(inner, text="", bg=BG_CARD, fg=FG,
                                      font=(self.family, f(11)), anchor="w")
        self.version_label.pack(anchor="w")

        # The notes of the release, when there are any.
        self.notes = tk.Text(inner, bg=BG_FIELD, fg=FG_DIM, height=6, bd=0,
                             highlightthickness=1, highlightbackground=BG_BORDER,
                             highlightcolor=BG_BORDER, font=(self.family, f(9)),
                             wrap="word", state="disabled", padx=s(12),
                             pady=s(10), relief="flat")
        self.notes.pack(fill="both", expand=True, pady=(s(12), 0))

        # The bar that shows how far the download got.
        self.progress = tk.Canvas(inner, bg=PROGRESS_TRACK, height=s(6),
                                  highlightthickness=0, bd=0)
        self.progress.pack(fill="x", pady=(s(12), 0))
        self.progress.pack_forget()
        self._progress_value = 0.0

        # The row that holds the buttons of the card.
        self.actions = tk.Frame(inner, bg=BG_CARD)
        self.actions.pack(fill="x", pady=(s(14), 0))

        # The button that starts the update.
        self.install_button = GlassButton(
            self.actions, "立即更新", self.family, self.dpi,
            command=self._install, accent=True, background=BG_CARD)
        self.install_button.pack(side="right")

        # The button that opens the page of the release.
        self.setup_button = GlassButton(
            self.actions, "下载安装包", self.family, self.dpi,
            command=self._download_setup, background=BG_CARD)
        self.setup_button.pack(side="right", padx=(0, s(8)))

        # ---- The buttons ----
        tk.Frame(self, bg=BG_DIVIDER, height=1).pack(fill="x", side="bottom")
        footer = tk.Frame(self, bg=BG, height=s(50))
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        self.close_button = GlassButton(footer, "关闭", self.family, self.dpi,
                                        command=self._close,
                                        background=BG)
        self.close_button.pack(side="right", padx=(0, s(18)), pady=s(10))

        # The link that opens the release in the browser. It sits in the
        # footer, on the left, so it does not disturb the buttons.
        self.link_button = tk.Label(
            footer, text="在浏览器中查看发行说明", bg=BG, fg=ACCENT,
            font=(self.family, f(9)), cursor="hand2")
        self.link_button.pack(side="left", padx=s(18))
        self.link_button.bind("<Button-1>", lambda _e: self._download())

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _draw_badge(self, color: str, mark: str) -> None:
        """Draws the round badge next to the heading."""
        _badge(self.badge, self._s(40), color, mark)

    def _relayout(self) -> None:
        """Sizes the card to its content and moves the window along.

        A card that is embedded in a canvas does not grow on its own, so
        the height is asked for again every time the content changes. The
        window is centred afterwards, because it grew.
        """
        self.card.refresh()
        self.update_idletasks()
        self._centre()

    def _centre(self) -> None:
        """Places the dialog in the middle of the screen.

        The window is as tall as its content, because the card decides
        itself how tall it has to be. A window that would not fit on a
        small screen is made smaller; the notes are scrolled in that case,
        so nothing is lost.
        """
        import ctypes

        self.update_idletasks()
        user32 = ctypes.WinDLL("user32")
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)

        width = self.winfo_reqwidth()
        height = self.winfo_reqheight()
        width = min(width, int(screen_w * 0.9))
        height = min(height, int(screen_h * 0.85))

        x = (screen_w - width) // 2
        y = (screen_h - height) // 3
        self.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")

    # ------------------------------------------------------------------
    # The result of the check
    # ------------------------------------------------------------------

    def show_up_to_date(self) -> None:
        """Says that the app already runs the newest version."""
        self.title_label.configure(text="已经是最新版本")
        self.message_label.configure(
            text=f"当前版本 {__version__}，没有找到更新的版本。")
        self.version_label.configure(text=f"当前版本  {__version__}")
        self._draw_badge(ACCENT, "check")
        self._hide_notes()
        self._hide_actions()
        self._relayout()

    def show_new_version(self, release) -> None:
        """Shows the release that was found."""
        self.release = release
        version = release.version.lstrip("vV")
        self.title_label.configure(text=f"发现新版本 {version}")
        self.message_label.configure(
            text=f"当前版本 {__version__}，可以更新到 {version}。")
        self.version_label.configure(
            text=f"当前版本  {__version__}          最新版本  {version}")
        self._draw_badge(WARNING, "up")
        self._show_notes(release.notes)
        self.actions.pack(fill="x", pady=(self._s(14), 0))
        self.link_button.pack(side="left", padx=self._s(18))
        self.install_button.set_text("立即更新")
        self.install_button.set_enabled(True)
        if release.setup_url:
            self.setup_button.pack(side="right", padx=(0, self._s(8)))
        else:
            self.setup_button.pack_forget()
        self._relayout()

    def show_failed(self, reason: str) -> None:
        """Says that the check did not work out."""
        self.title_label.configure(text="检查更新失败")
        self.message_label.configure(text=reason)
        self.version_label.configure(text="")
        self._draw_badge(DANGER, "bang")
        self._hide_notes()
        self._hide_actions()
        self._relayout()

    def _hide_actions(self) -> None:
        """Hides the buttons that do not belong to the state."""
        self.install_button.set_enabled(False)
        self.actions.pack_forget()
        self.link_button.pack_forget()

    def _show_notes(self, text: str) -> None:
        """Fills the box with the notes of the release."""
        if not text or not text.strip():
            self._hide_notes()
            return
        self.notes.configure(state="normal")
        self.notes.delete("1.0", "end")
        self.notes.insert("1.0", text.strip())
        self.notes.configure(state="disabled")
        self.notes.pack(fill="both", expand=True, pady=(self._s(12), 0))

    def _hide_notes(self) -> None:
        """Hides the box with the notes."""
        self.notes.configure(state="normal")
        self.notes.delete("1.0", "end")
        self.notes.configure(state="disabled")
        self.notes.pack_forget()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _install(self) -> None:
        """Downloads the new version and puts it in place.

        The app closes itself once the new file is ready, and the helper
        starts the new copy.
        """
        if self.release is None:
            return
        if self.on_install is None:
            # Without a way to install, the browser is the fallback.
            self._download()
            return

        self.install_button.set_enabled(False)
        self.install_button.set_text("正在更新…")
        self.setup_button.set_enabled(False)
        self.title_label.configure(text="正在下载更新…")
        self.message_label.configure(text="请不要关闭程序，下载完成后会自动重启。")
        self._draw_badge(ACCENT, "down")
        self.link_button.pack_forget()
        self.progress.pack(fill="x", pady=(self._s(12), 0))
        self._set_progress(0.0)
        self._relayout()

        self.on_install(self.release, self._on_progress, self._on_installed,
                        self._on_install_failed)

    def _on_progress(self, read: int, total: int) -> None:
        """Shows how far the download got."""
        if total:
            self._set_progress(read / total)
        else:
            # Without a size the bar cannot show a percentage, so it moves
            # a little with every chunk.
            self._progress_value = min(0.99, self._progress_value + 0.02)
            self._set_progress(self._progress_value)

    def _set_progress(self, value: float) -> None:
        """Draws the bar."""
        self._progress_value = max(0.0, min(1.0, value))
        self.progress.delete("all")
        width = max(1, self.progress.winfo_width())
        height = max(1, self.progress.winfo_height())
        filled = int(width * self._progress_value)
        if filled > 0:
            self.progress.create_polygon(
                rounded_points(0, 0, filled, height, height / 2),
                fill=ACCENT, outline="")

    def _on_installed(self) -> None:
        """The new file is in place; the app is about to close."""
        self.title_label.configure(text="更新完成")
        self.message_label.configure(text="正在重启…")
        self.install_button.set_enabled(False)
        self.install_button.set_text("正在重启…")
        self._draw_badge(ACCENT, "check")
        self._set_progress(1.0)

    def _on_install_failed(self, reason: str) -> None:
        """The update did not work out."""
        self.title_label.configure(text="更新失败")
        self.message_label.configure(text=reason)
        self._draw_badge(DANGER, "bang")
        self.install_button.set_enabled(True)
        self.install_button.set_text("重试")
        self.setup_button.set_enabled(True)
        self.link_button.pack(side="left", padx=self._s(18))
        self.progress.pack_forget()
        self._relayout()

    def _download(self) -> None:
        """Opens the download page of the release in the browser."""
        if self.release is None:
            return
        try:
            webbrowser.open(self.release.download_url)
        except Exception:
            pass

    def _download_setup(self) -> None:
        """Opens the installer of the release in the browser."""
        if self.release is None or not self.release.setup_url:
            return
        try:
            webbrowser.open(self.release.setup_url)
        except Exception:
            pass

    def _close(self) -> None:
        """Closes the dialog."""
        if self._closed:
            return
        self._closed = True
        self.destroy()
