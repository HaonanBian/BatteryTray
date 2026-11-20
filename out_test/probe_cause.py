"""Shows why the footer of the window stops following it.

A frame with ``pack_propagate(False)`` keeps the height it was given.
When the packer has to shrink the window, it cannot shrink that frame
below the height its children ask for, so the frame keeps its old size
and ends up outside of the window.
"""

from __future__ import annotations

import time

import tkinter as tk


def settle(root, rounds=30):
    """Lets Tk finish the layout."""
    for _ in range(rounds):
        root.update_idletasks()
        root.update()
        time.sleep(0.005)


def build(root, footer_height, propagate):
    """Builds a header, a list and a footer."""
    header = tk.Frame(root, bg="red", height=58)
    header.pack(fill="x", side="top")
    header.pack_propagate(False)

    list_wrap = tk.Frame(root, bg="blue")
    list_wrap.pack(fill="both", expand=True)

    footer = tk.Frame(root, bg="green", height=footer_height)
    footer.pack(fill="x", side="bottom")
    if propagate:
        footer.pack_propagate(False)
    tk.Label(footer, text="summary").pack(side="left")
    tk.Button(footer, text="设置").pack(side="right")
    return footer


def main() -> None:
    """Compares the footer with and without a fixed height."""
    import time

    for propagate in (False, True):
        root = tk.Tk()
        root.geometry("900x700")
        footer = build(root, 63, propagate)
        settle(root)
        print(f"=== pack_propagate(False)={propagate}")
        print(f"   at 900x700: footer={footer.winfo_geometry()} "
              f"req_h={footer.winfo_reqheight()} "
              f"children_need={footer.winfo_children()[0].winfo_reqheight()}")
        root.geometry("700x500")
        settle(root)
        print(f"   at 700x500: footer={footer.winfo_geometry()}")
        root.destroy()


if __name__ == "__main__":
    main()
