"""Helpers for the dialogs of the app.

A window that belongs to another window is only shown while that other
window is on screen. The main window of the app is hidden most of the
time, because the app lives in the notification area, so a dialog that
is tied to it would never become visible: the user would click a button,
nothing would happen and the app would wait for a window that never
shows up.

The dialogs are therefore only made transient for a master that is
really on screen. Without an owner they are ordinary windows that stay
visible on their own.
"""

from __future__ import annotations

import tkinter as tk

from .dwm import style_window


def prepare_dialog(dialog: tk.Toplevel, master: tk.Misc | None = None) -> None:
    """Makes a dialog ready to be shown.

    The dialog is put on top of the other windows, gets the dark title bar
    of the app and is bound to the master only when the master is on
    screen. A dialog without an owner keeps showing itself, even when the
    window it was opened from is hidden in the meantime.
    """
    # The dialog has to stay on top of the borderless popup and of the
    # main window.
    dialog.attributes("-topmost", True)

    if master is not None and master.winfo_viewable():
        dialog.transient(master)
    else:
        # An empty master removes the owner. The dialog then behaves like
        # an ordinary window instead of waiting for a hidden master.
        dialog.transient("")

    # The title bar of Windows is white and does not fit to the dark
    # dialog.
    style_window(dialog)

    # The dialog is put in front once it is on screen. The window it was
    # opened from may be on top of it otherwise, which would hide the
    # dialog behind the popup of the tray.
    dialog.after_idle(dialog.lift)
