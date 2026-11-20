"""The window that reports the result of an update check.

The layout follows the software update panel of the system settings: a
round badge with the app icon, a heading, a card that holds the version
numbers and the button that starts the update, and a link underneath that
opens the page of the release in the browser.

The dark colours of the app are kept, only the arrangement comes from that
panel. The panel has three states: it is looking for a new release, it
found one, or the check failed. When the update runs, the panel turns
into a progress view that reports how far the download got and restarts
the app when it is done.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
import webbrowser

from . import __version__
from .dialog import prepare_dialog
from .dpi import scale_font, scale_pixels
from .widgets import rounded_points

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


def pick_font_family(root: tk.Misc) -> str:
    """Chooses the best UI font available on this system."""
    available = set(tkfont.families(root))
    for name in ("Microsoft YaHei UI", "Segoe UI", "Tahoma"):
        if name in available:
            return name
    return "TkDefaultFont"


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

        self.title("检查更新")
        self.configure(bg=BG)
        self.resizable(False, False)
        prepare_dialog(self, master)

        s = lambda px: scale_pixels(px, dpi)  # noqa: E731
        f = lambda pt: scale_font(pt, dpi)  # noqa: E731
        # The helpers are kept, so the later methods can use them too.
        self._s = s
        self._f = f

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=s(22), pady=s(20))

        # ---- The heading with the round badge ----
        head = tk.Frame(body, bg=BG)
        head.pack(fill="x")

        self.badge = tk.Canvas(head, bg=BG, highlightthickness=0, bd=0,
                                width=s(46), height=s(46))
        self.badge.pack(side="left")
        self._draw_badge(ACCENT, "↑")

        heading = tk.Frame(head, bg=BG)
        heading.pack(side="left", padx=(s(12), 0), fill="x", expand=True)

        self.title_label = tk.Label(heading, text="正在检查更新…", bg=BG,
                                    fg=FG, font=(family, f(12), "bold"),
                                    anchor="w")
        self.title_label.pack(anchor="w")

        self.message_label = tk.Label(
            heading, text="正在连接 GitHub，请稍候…", bg=BG, fg=FG_DIM,
            font=(family, f(9)), anchor="w", justify="left")
        self.message_label.pack(anchor="w", pady=(s(4), 0))

        # ---- The card with the version numbers ----
        self.card = tk.Frame(body, bg=BG_CARD)
        self.card.pack(fill="x", pady=(s(16), 0))

        inner = tk.Frame(self.card, bg=BG_CARD)
        inner.pack(fill="x", padx=s(16), pady=s(14))

        self.version_label = tk.Label(inner, text="", bg=BG_CARD, fg=FG,
                                      font=(family, f(9)), anchor="w")
        self.version_label.pack(anchor="w")

        # The notes of the release, when there are any.
        self.notes = tk.Text(inner, bg=BG_FIELD, fg=FG_DIM, height=5, bd=0,
                             highlightthickness=1, highlightbackground=BG_BORDER,
                             font=(family, f(8)), wrap="word", state="disabled",
                             padx=s(10), pady=s(8))
        self.notes.pack(fill="both", expand=True, pady=(s(10), 0))

        # The row that holds the buttons. The accent button sits on the
        # right, the other one next to it.
        self.actions = tk.Frame(inner, bg=BG_CARD)
        self.actions.pack(fill="x", pady=(s(12), 0))

        # The button that starts the update.
        self.install_button = tk.Button(
            self.actions, text="立即更新", bg=ACCENT, fg="#101113",
            activebackground="#00F07F", activeforeground="#101113",
            relief="flat", bd=0, cursor="hand2", font=(family, f(9), "bold"),
            padx=s(14), pady=s(7),
            command=self._install)
        self.install_button.pack(side="right")

        # The button that opens the page of the release.
        self.setup_button = tk.Button(
            self.actions, text="下载安装包", bg=BG_CARD, fg=FG_DIM,
            activebackground="#25272B", activeforeground=FG,
            relief="flat", bd=0, cursor="hand2", font=(family, f(8)),
            padx=s(10), pady=s(5),
            command=self._download_setup)
        self.setup_button.pack(side="right", padx=(0, s(8)))

        # ---- The link that opens the release in the browser ----
        self.link_button = tk.Label(
            body, text="在浏览器中查看发行说明", bg=BG, fg=ACCENT,
            font=(family, f(8)), cursor="hand2")
        self.link_button.pack(anchor="w", pady=(s(12), 0))
        self.link_button.bind("<Button-1>", lambda _e: self._download())

        # ---- The bar that shows how far the download got ----
        self.progress = tk.Canvas(body, bg=BG_CARD, height=s(6),
                                  highlightthickness=0, bd=0)
        self.progress.pack(fill="x", pady=(s(14), 0))
        self.progress.pack_forget()
        self._progress_value = 0.0

        tk.Frame(self, bg="#232428", height=1).pack(fill="x", side="bottom")
        buttons = tk.Frame(self, bg=BG)
        buttons.pack(fill="x", side="bottom", padx=s(22), pady=s(16))

        self.close_button = tk.Button(
            buttons, text="关闭", bg="#24262A", fg=FG_DIM,
            activebackground="#2E3136", activeforeground=FG,
            relief="flat", bd=0, cursor="hand2", font=(family, f(9)),
            padx=s(14), pady=s(6),
            command=self._close)
        self.close_button.pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.update_idletasks()
        self._centre()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _draw_badge(self, color: str, mark: str) -> None:
        """Draws the round badge next to the heading.

        The mark inside the badge is drawn as a shape and not as a letter,
        because a font does not have to bring the arrow along.
        """
        self.badge.delete("all")
        size = self._s(46)
        radius = size / 2
        # The circle is a little smaller than the badge, so it is not cut
        # off at the edge.
        inset = size * 0.06
        self.badge.create_polygon(
            rounded_points(inset, inset, size - inset, size - inset,
                           radius - inset),
            fill=color, outline="")

        middle = size / 2
        if mark == "✓":
            # A check that is drawn as two strokes.
            self.badge.create_line(size * 0.34, middle,
                                   size * 0.46, size * 0.62,
                                   fill="#101113", width=max(2, size * 0.09),
                                   capstyle="round", joinstyle="round")
            self.badge.create_line(size * 0.46, size * 0.62,
                                   size * 0.68, size * 0.38,
                                   fill="#101113", width=max(2, size * 0.09),
                                   capstyle="round", joinstyle="round")
        elif mark == "!":
            # A bar with a dot underneath it.
            bar = size * 0.09
            self.badge.create_polygon(
                rounded_points(middle - bar / 2, size * 0.28,
                               middle + bar / 2, size * 0.56, bar / 2),
                fill="#101113", outline="")
            self.badge.create_oval(middle - bar / 2, size * 0.64,
                                   middle + bar / 2, size * 0.64 + bar,
                                   fill="#101113", outline="")
        else:
            # An arrow that points up, or down when the file is fetched.
            up = mark == "↑"
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
            self.badge.create_polygon(points, fill="#101113", outline="")

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

    # ------------------------------------------------------------------
    # The result of the check
    # ------------------------------------------------------------------

    def show_up_to_date(self) -> None:
        """Says that the app already runs the newest version."""
        self.title_label.configure(text="已经是最新版本")
        self.message_label.configure(
            text=f"当前版本 {__version__}，没有找到更新的版本。")
        self.version_label.configure(text=f"当前版本  {__version__}")
        self._draw_badge(ACCENT, "✓")
        self._hide_notes()
        self._hide_actions()

    def show_new_version(self, release) -> None:
        """Shows the release that was found."""
        self.release = release
        version = release.version.lstrip("vV")
        self.title_label.configure(text=f"发现新版本 {version}")
        self.message_label.configure(
            text=f"当前版本 {__version__}，可以更新到 {version}。")
        self.version_label.configure(
            text=f"当前版本  {__version__}          最新版本  {version}")
        self._draw_badge(WARNING, "↑")
        self._show_notes(release.notes)
        self.actions.pack(fill="x", pady=(self._s(12), 0))
        self.link_button.pack(anchor="w", pady=(self._s(12), 0))
        self.install_button.configure(state="normal", text="立即更新")
        if release.setup_url:
            self.setup_button.pack(side="right", padx=(0, self._s(8)))
        else:
            self.setup_button.pack_forget()

    def show_failed(self, reason: str) -> None:
        """Says that the check did not work out."""
        self.title_label.configure(text="检查更新失败")
        self.message_label.configure(text=reason)
        self.version_label.configure(text="")
        self._draw_badge(DANGER, "!")
        self._hide_notes()
        self._hide_actions()

    def _hide_actions(self) -> None:
        """Hides the buttons that do not belong to the state."""
        self.install_button.configure(state="disabled")
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
        self.notes.pack(fill="both", expand=True, pady=(self._s(10), 0))

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

        self.install_button.configure(state="disabled", text="正在更新…")
        self.setup_button.configure(state="disabled")
        self.title_label.configure(text="正在下载更新…")
        self.message_label.configure(text="请不要关闭程序，下载完成后会自动重启。")
        self._draw_badge(ACCENT, "↓")
        self.link_button.pack_forget()
        self.progress.pack(fill="x", pady=(self._s(14), 0))
        self._set_progress(0.0)

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
        self.install_button.configure(state="disabled", text="正在重启…")
        self._draw_badge(ACCENT, "✓")
        self._set_progress(1.0)

    def _on_install_failed(self, reason: str) -> None:
        """The update did not work out."""
        self.title_label.configure(text="更新失败")
        self.message_label.configure(text=reason)
        self._draw_badge(DANGER, "!")
        self.install_button.configure(state="normal", text="重试")
        self.setup_button.configure(state="normal")
        self.link_button.pack(anchor="w", pady=(self._s(12), 0))
        self.progress.pack_forget()

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
