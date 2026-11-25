"""The window that shows the diagnostic report.

The user opens it from the settings window when a device does not show up.
The report is built in the background, because asking the drivers takes a
moment and the window must not freeze while it happens.

The report can be copied to the clipboard, saved to a file or opened as an
issue on GitHub, so that the user can hand it over without having to hunt
for the file.
"""

from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path

from . import __version__
from .dialog import prepare_dialog
from .dpi import scale_font, scale_pixels
from .update import REPO_NAME, REPO_OWNER
from .widgets import (
    ACCENT,
    BG,
    BG_BORDER,
    BG_DIVIDER,
    BG_FIELD,
    FG,
    FG_DIM,
    FG_MUTED,
    GlassButton,
    rounded_points,
)

# The ink on top of the accent colour of a button.
ACCENT_INK = "#142019"
# The ink of the marks that are drawn on the badge.
BADGE_INK = "#20252C"

# The page the issue is opened on.
ISSUE_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/issues/new"

# How much of the report fits into the address of the browser. The text is
# escaped before it is put into the address, and the escaping can make it
# twice as long, so the room is kept small enough for that.
BODY_LIMIT = 2000


def _badge(canvas: tk.Canvas, size: float, color: str) -> None:
    """Draws the round badge of the heading.

    The mark is a small document with three lines on it, because a font
    does not have to bring the glyph along.
    """
    canvas.delete("all")
    inset = size * 0.06
    canvas.create_polygon(
        rounded_points(inset, inset, size - inset, size - inset,
                       size / 2 - inset),
        fill=color, outline="")

    middle = size / 2
    # The body of the document.
    width = size * 0.34
    top = size * 0.26
    bottom = size * 0.74
    left = middle - width / 2
    canvas.create_polygon(
        rounded_points(left, top, left + width, bottom, size * 0.05),
        outline=BADGE_INK, width=max(2, size * 0.07))
    # The three lines on it.
    for index in range(3):
        y = top + size * (0.14 + index * 0.14)
        canvas.create_line(left + size * 0.08, y,
                           left + width - size * 0.08, y,
                           fill=BADGE_INK, width=max(1.5, size * 0.05),
                           capstyle="round")


class DiagnosticDialog(tk.Toplevel):
    """Shows the diagnostic report and the ways to hand it over."""

    def __init__(self, master: tk.Misc, family: str, dpi: float):
        super().__init__(master)
        self.dpi = dpi
        self.family = family
        # The report, once it has been built.
        self.report: str | None = None
        # The path of the file the report was saved to.
        self.saved_to: str | None = None

        self.title("BatteryTray 诊断")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(scale_pixels(520, dpi), scale_pixels(400, dpi))
        self.geometry(f"{scale_pixels(660, dpi)}x{scale_pixels(560, dpi)}")
        prepare_dialog(self, master)

        self._build()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.update_idletasks()
        self._centre()
        self.after_idle(self.focus_set)
        # The report is built in the background, so that the window shows up
        # right away instead of waiting for the drivers.
        self.after(60, self._build_report)

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def _build(self) -> None:
        """Builds the heading, the report box and the buttons."""
        s = lambda px: scale_pixels(px, self.dpi)  # noqa: E731
        f = lambda pt: scale_font(pt, self.dpi)  # noqa: E731

        # ---- The heading with the round badge ----
        header = tk.Frame(self, bg=BG, height=s(64))
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        badge = tk.Canvas(header, bg=BG, highlightthickness=0, bd=0,
                          width=s(40), height=s(40))
        badge.pack(side="left", padx=(s(18), 0), pady=s(12))
        _badge(badge, s(40), ACCENT)

        heading = tk.Frame(header, bg=BG)
        heading.pack(side="left", padx=(s(12), 0), fill="x", expand=True)
        tk.Label(heading, text="诊断", bg=BG, fg=FG,
                 font=(self.family, f(15), "bold"),
                 anchor="w").pack(anchor="w")
        self.subtitle = tk.Label(heading, text="正在读取设备…", bg=BG,
                                 fg=FG_MUTED, font=(self.family, f(9)),
                                 anchor="w")
        self.subtitle.pack(anchor="w", pady=(s(1), 0))

        tk.Frame(self, bg=BG_DIVIDER, height=1).pack(fill="x", side="top")

        # ---- The report ----
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        self.text = tk.Text(body, bg=BG_FIELD, fg=FG_DIM, height=12, bd=0,
                            highlightthickness=1, highlightbackground=BG_BORDER,
                            highlightcolor=BG_BORDER,
                            font=("Consolas", f(9)), wrap="none",
                            state="disabled", padx=s(12), pady=s(10),
                            relief="flat")
        self.text.pack(fill="both", expand=True, padx=s(18), pady=s(16))

        # ---- The buttons ----
        tk.Frame(self, bg=BG_DIVIDER, height=1).pack(fill="x", side="bottom")
        footer = tk.Frame(self, bg=BG, height=s(50))
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        GlassButton(footer, "关闭", self.family, self.dpi,
                    command=self.destroy,
                    background=BG).pack(side="right", padx=(0, s(18)),
                                        pady=s(10))

        self.issue_button = GlassButton(
            footer, "打开问题反馈", self.family, self.dpi,
            command=self._open_issue, accent=True, background=BG)
        self.issue_button.pack(side="right", padx=(0, s(10)), pady=s(10))
        self.issue_button.set_enabled(False)

        self.save_button = GlassButton(
            footer, "保存为文件", self.family, self.dpi,
            command=self._save, background=BG)
        self.save_button.pack(side="right", padx=(0, s(10)), pady=s(10))
        self.save_button.set_enabled(False)

        self.copy_button = GlassButton(
            footer, "复制到剪贴板", self.family, self.dpi,
            command=self._copy, background=BG)
        self.copy_button.pack(side="right", padx=(0, s(10)), pady=s(10))
        self.copy_button.set_enabled(False)

    # ------------------------------------------------------------------
    # The report
    # ------------------------------------------------------------------

    def _build_report(self) -> None:
        """Asks the drivers what they can see and shows the answer."""
        from .diagnostics import build_report

        try:
            self.report = build_report()
        except Exception as error:
            self.report = f"诊断失败：{error}"
        self._show(self.report)

        self.copy_button.set_enabled(True)
        self.save_button.set_enabled(True)
        self.issue_button.set_enabled(True)
        self.subtitle.configure(
            text="把下面的内容发给我，就能找到问题所在")

    def _show(self, text: str) -> None:
        """Puts the report into the box."""
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)
        self.text.configure(state="disabled")

    # ------------------------------------------------------------------
    # Handing the report over
    # ------------------------------------------------------------------

    def _copy(self) -> None:
        """Puts the report into the clipboard."""
        if not self.report:
            return
        self.clipboard_clear()
        self.clipboard_append(self.report)
        self.subtitle.configure(text="已复制到剪贴板，粘贴给我就行")

    def _save(self) -> None:
        """Asks for a place and writes the report there."""
        if not self.report:
            return
        from tkinter import filedialog

        stamp = _stamp()
        path = filedialog.asksaveasfilename(
            parent=self,
            title="保存诊断报告",
            defaultextension=".txt",
            initialfile=f"BatteryTray-诊断-{stamp}.txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            Path(path).write_text(self.report, encoding="utf-8")
        except OSError as error:
            self.subtitle.configure(text=f"保存失败：{error}")
            return
        self.saved_to = path
        self.subtitle.configure(text=f"已保存到 {path}")

    def _open_issue(self) -> None:
        """Opens the page of a new issue with the report in it.

        The report is put into the body of the issue. A browser only
        takes an address of a few thousand characters, so a long report
        is shortened. The important parts are kept and the whole report
        is written to a file, so that nothing is really lost.
        """
        if not self.report:
            return
        title = f"诊断报告 · v{__version__} · {_stamp()}"
        body = self.report

        # A long body does not fit into the address of the browser, so it
        # is shortened and the whole report is saved next to the program.
        if len(body) > BODY_LIMIT:
            saved = self._save_quietly()
            body = _shorten(body) + ("\n\n…（报告太长，"
                                     "完整内容在 " + saved + "）")
        url = f"{ISSUE_URL}?title={_quote(title)}&body={_quote(body)}"
        try:
            os.startfile(url)  # noqa: S606 - the browser opens the page
        except Exception as error:
            self.subtitle.configure(text=f"打开浏览器失败：{error}")
            return
        self.subtitle.configure(text="已在浏览器中打开，请把内容提交")

    def _save_quietly(self) -> str:
        """Writes the report to a file without asking, and returns the path."""
        from .config import config_dir

        directory = config_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"diagnostic-{_stamp()}.txt"
        path.write_text(self.report or "", encoding="utf-8")
        return str(path)

    # ------------------------------------------------------------------
    # Placing
    # ------------------------------------------------------------------

    def _centre(self) -> None:
        """Places the dialog in the middle of the screen."""
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


def _stamp() -> str:
    """The name of this moment, for the name of a file."""
    import datetime

    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def _shorten(report: str) -> str:
    """Shortens the report so that it fits into the address of a browser.

    The parts that say what went wrong are kept: the machine, the answer
    of every driver and the devices that are finally shown. The long list
    of the HID interfaces is the first thing to go, because it is the
    least telling one.
    """
    if len(report) <= BODY_LIMIT:
        return report

    # The report is cut into its parts, so that the ones that matter can
    # be kept and the rest can be left out.
    parts = report.split("=" * 60)
    # Every other part is a heading, the ones in between are its text.
    titles = parts[1::2]
    texts = parts[2::2]

    kept: list[str] = []
    for title, text in zip(titles, texts):
        if "HID 子系统" in title:
            # Only the number of the interfaces and the reason they are
            # missing are worth keeping.
            lines = [line for line in text.splitlines()
                     if "接口数" in line or "报错" in line
                     or "没有接口" in line]
            kept.append(title + "\n" + "\n".join(lines))
            continue
        if "每个驱动" in title:
            # The stack traces of a failed driver are long, but they say
            # exactly why the driver failed.
            kept.append(title + "\n" + text)
            continue
        kept.append(title + "\n" + text)

    result = "=" * 60 + "=" * 60 + "".join(kept)
    if len(result) > BODY_LIMIT:
        result = result[:BODY_LIMIT]
    return result


def _quote(text: str) -> str:
    """Encodes the text so that it can be put into an address."""
    from urllib.parse import quote

    return quote(text, safe="")


def ask_diagnostic(master: tk.Misc, family: str, dpi: float) -> None:
    """Shows the diagnostic window."""
    dialog = DiagnosticDialog(master, family, dpi)
    master.wait_window(dialog)
