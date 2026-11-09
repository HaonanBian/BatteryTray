"""A small dialog that asks for a new device name.

The dialog is used by the main window and by the quick popup, so the rename
works the same way in both places.
"""

from __future__ import annotations

import tkinter as tk

from .dpi import scale_font, scale_pixels

BG = "#17181B"
BG_FIELD = "#101113"
BG_BORDER = "#34363B"
FG = "#EDEDED"
FG_DIM = "#9C9EA3"
FG_MUTED = "#9C9EA3"
ACCENT = "#00E676"


class RenameDialog(tk.Toplevel):
    """Asks the user for a new name for a device."""

    def __init__(self, master: tk.Misc, family: str, dpi: float,
                 original_name: str, current_name: str):
        super().__init__(master)
        self.dpi = dpi
        self.family = family
        self.result: str | None = None

        self.title("重命名设备")
        self.configure(bg=BG)
        self.resizable(False, False)
        # The dialog has to stay on top of the borderless popup.
        self.attributes("-topmost", True)
        self.transient(master)

        pad = scale_pixels(18, dpi)

        tk.Label(self, text="设备名称", bg=BG, fg=FG_MUTED,
                 font=(family, scale_font(8, dpi))).pack(
                     anchor="w", padx=pad, pady=(pad, scale_pixels(6, dpi)))

        self.entry = tk.Entry(self, bg=BG_FIELD, fg=FG, insertbackground=ACCENT,
                              relief="flat", bd=0, highlightthickness=1,
                              highlightbackground=BG_BORDER,
                              highlightcolor=ACCENT,
                              font=(family, scale_font(10, dpi)))
        self.entry.pack(fill="x", padx=pad)
        self.entry.insert(0, current_name)
        self.entry.select_range(0, "end")

        tk.Label(self, text=f"原名称：{original_name}", bg=BG, fg=FG_MUTED,
                 font=(family, scale_font(7, dpi)), wraplength=scale_pixels(260, dpi),
                 justify="left").pack(
                     anchor="w", padx=pad,
                     pady=(scale_pixels(8, dpi), 0))

        buttons = tk.Frame(self, bg=BG)
        buttons.pack(fill="x", padx=pad, pady=(scale_pixels(14, dpi), pad))

        tk.Button(buttons, text="恢复默认", bg="#232529", fg=FG_DIM,
                  activebackground="#2E3035", activeforeground=FG,
                  relief="flat", bd=0, cursor="hand2",
                  font=(family, scale_font(9, dpi)),
                  command=self._reset).pack(side="left")

        tk.Button(buttons, text="取消", bg="#232529", fg=FG_DIM,
                  activebackground="#2E3035", activeforeground=FG,
                  relief="flat", bd=0, cursor="hand2",
                  font=(family, scale_font(9, dpi)),
                  command=self._cancel).pack(side="right")

        tk.Button(buttons, text="保存", bg=ACCENT, fg="#101113",
                  activebackground="#00F07F", activeforeground="#101113",
                  relief="flat", bd=0, cursor="hand2",
                  font=(family, scale_font(9, dpi), "bold"),
                  command=self._confirm).pack(side="right",
                                              padx=(0, scale_pixels(8, dpi)))

        self.bind("<Return>", lambda _event: self._confirm())
        self.bind("<Escape>", lambda _event: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self.entry.focus_set()
        self.update_idletasks()
        self._centre()
        self.entry.focus_set()

    def _centre(self) -> None:
        """Places the dialog in the middle of the screen."""
        self.update_idletasks()
        width = self.winfo_reqwidth()
        height = self.winfo_reqheight()
        import ctypes

        screen_w = ctypes.WinDLL("user32").GetSystemMetrics(0)
        screen_h = ctypes.WinDLL("user32").GetSystemMetrics(1)
        x = (screen_w - width) // 2
        y = (screen_h - height) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _confirm(self) -> None:
        """Accepts the new name."""
        self.result = self.entry.get().strip()
        self.destroy()

    def _cancel(self) -> None:
        """Closes the dialog without changing anything."""
        self.result = None
        self.destroy()

    def _reset(self) -> None:
        """Clears the field so the original name is restored."""
        self.entry.delete(0, "end")
        self.entry.focus_set()


def ask_rename(master: tk.Misc, family: str, dpi: float,
               original_name: str, current_name: str) -> str | None:
    """Shows the rename dialog and returns the new name.

    ``None`` means the user cancelled the dialog.
    """
    dialog = RenameDialog(master, family, dpi, original_name, current_name)
    master.wait_window(dialog)
    return dialog.result
