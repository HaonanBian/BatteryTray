"""The installation wizard.

A small window that walks the user through the installation: where to put
the program, which shortcuts to create and whether to start with Windows.
The same program is used for the uninstaller, which is what "Apps and
features" calls.
"""

from __future__ import annotations

import ctypes
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from . import payload

BG = "#111113"
BG_CARD = "#1C1D20"
BG_FIELD = "#101113"
BG_BORDER = "#2E3035"
FG = "#EDEDED"
FG_DIM = "#9C9EA3"
FG_MUTED = "#6A6C71"
ACCENT = "#00E676"

APP_NAME = payload.APP_NAME
APP_VERSION = payload.APP_VERSION


def pick_font_family(root: tk.Misc) -> str:
    """Chooses the best UI font available on this system."""
    available = set(tkfont.families(root))
    for name in ("Microsoft YaHei UI", "Segoe UI", "Tahoma"):
        if name in available:
            return name
    return "TkDefaultFont"


def set_dpi_aware() -> None:
    """Declares the process DPI aware so the window stays sharp."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


class InstallerWindow(tk.Tk):
    """The installation wizard."""

    def __init__(self, uninstall: bool = False):
        set_dpi_aware()
        super().__init__()

        self.uninstall = uninstall
        self.family = pick_font_family(self)
        self.title(f"{'卸载' if uninstall else '安装'} {APP_NAME}")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._close)

        self._worker: threading.Thread | None = None
        self._done = False
        self._queue: queue.Queue = queue.Queue()
        self._log: tk.Text | None = None

        self._build()
        self.update_idletasks()
        self._centre()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self) -> None:
        pad = 24
        f = lambda pt: max(9, int(pt * 1.0))  # noqa: E731

        header = tk.Frame(self, bg=BG_CARD, height=72)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(header, text=APP_NAME, bg=BG_CARD, fg=ACCENT,
                 font=(self.family, 13, "bold")).pack(
                     anchor="w", padx=pad, pady=(14, 0))
        subtitle = ("卸载程序" if self.uninstall
                    else "鼠标与耳机电量 · 版本 " + APP_VERSION)
        tk.Label(header, text=subtitle, bg=BG_CARD, fg=FG_MUTED,
                 font=(self.family, 8)).pack(anchor="w", padx=pad,
                                            pady=(2, 14))

        self._build_footer()

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=pad, pady=pad)

        self._body = body
        if self.uninstall:
            self._build_uninstall_body(body)
        else:
            self._build_install_body(body)

    def _build_footer(self) -> None:
        """Adds the button row at the bottom of the window."""
        bar = tk.Frame(self, bg=BG_CARD, height=64)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self._cancel_button = tk.Button(
            bar, text="取消", command=self._close,
            bg="#24262A", fg=FG_DIM, activebackground="#2E3136",
            activeforeground=FG, relief="flat", bd=0, font=(self.family, 9),
            cursor="hand2", padx=20, pady=8, highlightthickness=0)
        self._cancel_button.pack(side="right", padx=(8, 20), pady=14)

        self._install_button = tk.Button(
            bar, text="卸载" if self.uninstall else "安装",
            command=self._start,
            bg=ACCENT, fg="#06210F", activebackground="#00F080",
            activeforeground="#06210F", relief="flat", bd=0,
            font=(self.family, 9, "bold"), cursor="hand2", padx=26, pady=8,
            highlightthickness=0)
        self._install_button.pack(side="right", pady=14)

    def _build_install_body(self, body: tk.Frame) -> None:
        f = self.family

        # ---- The install folder ----
        tk.Label(body, text="安装位置", bg=BG, fg=FG,
                 font=(f, 10, "bold")).pack(anchor="w")

        row = tk.Frame(body, bg=BG)
        row.pack(fill="x", pady=(8, 0))

        self.path_var = tk.StringVar(value=str(payload.default_install_dir()))
        self.path_entry = tk.Entry(row, textvariable=self.path_var,
                                   bg=BG_FIELD, fg=FG, insertbackground=ACCENT,
                                   relief="flat", bd=0, highlightthickness=1,
                                   highlightbackground=BG_BORDER,
                                   highlightcolor=ACCENT,
                                   font=(f, 9))
        self.path_entry.pack(side="left", fill="x", expand=True)

        tk.Button(row, text="浏览", command=self._browse,
                  bg="#24262A", fg=FG, activebackground="#2E3136",
                  activeforeground=ACCENT, relief="flat", bd=0,
                  font=(f, 9), cursor="hand2", padx=14, pady=6,
                  highlightthickness=0).pack(side="left", padx=(10, 0))

        tk.Label(body,
                 text="默认安装到当前用户目录，不需要管理员权限。",
                 bg=BG, fg=FG_MUTED, font=(f, 8)).pack(anchor="w", pady=(6, 0))

        # ---- The options ----
        tk.Frame(body, bg="#232428", height=1).pack(fill="x", pady=16)

        self.desktop_var = tk.BooleanVar(value=True)
        self.autostart_var = tk.BooleanVar(value=True)

        options = tk.Frame(body, bg=BG)
        options.pack(fill="x")

        tk.Checkbutton(options, text="创建桌面快捷方式",
                       variable=self.desktop_var, bg=BG, fg=FG,
                       activebackground=BG, activeforeground=FG,
                       selectcolor=BG_FIELD, highlightthickness=0, bd=0,
                       font=(f, 9), anchor="w").pack(fill="x", pady=3)

        tk.Checkbutton(options, text="开机自动启动（登录后自动运行）",
                       variable=self.autostart_var, bg=BG, fg=FG,
                       activebackground=BG, activeforeground=FG,
                       selectcolor=BG_FIELD, highlightthickness=0, bd=0,
                       font=(f, 9), anchor="w").pack(fill="x", pady=3)

    def _build_uninstall_body(self, body: tk.Frame) -> None:
        f = self.family
        location = payload.installed_location()

        tk.Label(body,
                 text=f"将移除 {APP_NAME} 的程序文件和快捷方式。",
                 bg=BG, fg=FG, font=(f, 9)).pack(anchor="w")
        if location:
            tk.Label(body, text=f"安装位置：{location}",
                     bg=BG, fg=FG_MUTED, font=(f, 8),
                     wraplength=400, justify="left").pack(anchor="w", pady=(8, 0))

        tk.Frame(body, bg="#232428", height=1).pack(fill="x", pady=16)

        self.settings_var = tk.BooleanVar(value=False)
        tk.Checkbutton(body, text="同时删除设置文件（恢复默认设置）",
                       variable=self.settings_var, bg=BG, fg=FG,
                       activebackground=BG, activeforeground=FG,
                       selectcolor=BG_FIELD, highlightthickness=0, bd=0,
                       font=(f, 9), anchor="w").pack(fill="x")

        self.folder_var = tk.StringVar()
        if location:
            self.folder_var.set(str(location))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _browse(self) -> None:
        """Lets the user pick the install folder."""
        from tkinter import filedialog

        chosen = filedialog.askdirectory(
            title="选择安装文件夹",
            initialdir=self.path_var.get(),
            mustexist=False)
        if chosen:
            self.path_var.set(chosen)

    def _centre(self) -> None:
        """Places the window in the middle of the screen."""
        self.update_idletasks()
        width = self.winfo_reqwidth()
        height = self.winfo_reqheight()
        screen_w = ctypes.windll.user32.GetSystemMetrics(0)
        screen_h = ctypes.windll.user32.GetSystemMetrics(1)
        x = (screen_w - width) // 2
        y = (screen_h - height) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _start(self) -> None:
        """Runs the installation in the background."""
        self._set_buttons_enabled(False)

        if self.uninstall:
            folder = self.folder_var.get() or str(payload.default_install_dir())
            remove_settings = self.settings_var.get()
            self._run(lambda progress: payload.uninstall(
                payload.Path(folder), remove_settings, progress))
        else:
            folder = self.path_var.get().strip()
            desktop = self.desktop_var.get()
            autostart = self.autostart_var.get()
            self._run(lambda progress: payload.install(
                payload.Path(folder), desktop, autostart, progress))

    def _run(self, work) -> None:
        """Runs the work in a thread and shows the result."""
        log = tk.Text(self, bg=BG_FIELD, fg=FG_DIM, height=7, bd=0,
                      highlightthickness=1, highlightbackground=BG_BORDER,
                      font=(self.family, 8), wrap="word")

        def thread_body() -> None:
            try:
                work(self._post_log)
            except Exception as exc:  # noqa: BLE001 - shown to the user
                self._post_log(f"出错了：{exc}")
            self._post_finished()

        self._log = log
        self._log.pack(fill="both", expand=True, pady=(14, 0))
        log.insert("end", "正在准备…\n")
        log.configure(state="disabled")

        self._worker = threading.Thread(target=thread_body, daemon=True)
        self._worker.start()

        # The worker only writes into the queue; the main loop moves the
        # messages into the log, because Tkinter is not thread safe.
        self.after(80, self._drain_queue)

    def _drain_queue(self) -> None:
        """Moves the queued messages into the log."""
        while True:
            try:
                message = self._queue.get_nowait()
            except queue.Empty:
                break
            if message is None:
                self._finish()
                continue
            self._append_log(message)

        if self._worker is not None and self._worker.is_alive():
            self.after(80, self._drain_queue)
        elif not self._done:
            # The worker ended without sending the final marker.
            self._finish()

    def _post_log(self, message: str) -> None:
        """Adds a line to the log; runs on the worker thread."""
        self._queue.put(message)

    def _append_log(self, message: str) -> None:
        """Shows a line in the log; runs on the main thread."""
        if self._log is None:
            return
        self._log.configure(state="normal")
        self._log.insert("end", message + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _post_finished(self) -> None:
        """Signals that the work is done; runs on the worker thread."""
        self._queue.put(None)

    def _finish(self) -> None:
        """Switches to the finished state; runs on the main thread."""
        self._done = True
        self._set_buttons_enabled(True)
        self._install_button.configure(text="完成", state="normal")
        self._install_button.configure(command=self._close)

        if self.uninstall:
            self._append_log("卸载完成。")
        else:
            self._append_log("安装完成，可以在开始菜单里启动。")

    def _set_buttons_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self._install_button.configure(state=state)
        self._cancel_button.configure(state=state)
        if hasattr(self, "path_entry"):
            self.path_entry.configure(state=state)
        for child in self.winfo_children():
            _set_state_recursive(child, state)

    def _close(self) -> None:
        """Closes the window."""
        if self._worker is not None and self._worker.is_alive():
            return
        self.destroy()


def _set_state_recursive(widget, state: str) -> None:
    """Turns a widget tree on or off."""
    try:
        if isinstance(widget, (tk.Entry, tk.Button, tk.Checkbutton)):
            widget.configure(state=state)
    except tk.TclError:
        pass
    for child in widget.winfo_children():
        _set_state_recursive(child, state)


def main() -> int:
    """Entry point of the installer."""
    # The uninstaller is the same program with a different flag.
    uninstall = "--uninstall" in sys.argv or "/uninstall" in sys.argv
    quiet = "--quiet" in sys.argv or "/quiet" in sys.argv
    silent = "--silent" in sys.argv or "/silent" in sys.argv

    if quiet:
        folder = payload.installed_location() or payload.default_install_dir()
        payload.uninstall(folder, False)
        return 0

    if silent:
        # Installs without showing anything; used for testing and for
        # deploying the app on a fleet of machines.
        folder = payload.default_install_dir()
        payload.install(folder, desktop_shortcut=True, autostart=True)
        return 0

    window = InstallerWindow(uninstall=uninstall)
    window.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
