"""Tries different ways of packing the three sections of the window.

The footer of the main window stops following the window when the window
becomes smaller. This script compares the orders in which the sections can
be packed.
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


def build(root, order):
    """Builds the three sections in the given order."""
    header = tk.Frame(root, bg="red", height=87)
    list_wrap = tk.Frame(root, bg="blue")
    footer = tk.Frame(root, bg="green", height=63)

    def add_header():
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

    def add_list():
        list_wrap.pack(fill="both", expand=True)

    def add_footer():
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

    for name in order:
        {"header": add_header, "list": add_list, "footer": add_footer}[name]()
    return header, list_wrap, footer


def main() -> None:
    """Runs the orders."""
    orders = [
        ("header", "list", "footer"),
        ("header", "footer", "list"),
        ("footer", "header", "list"),
    ]
    for order in orders:
        root = tk.Tk()
        root.geometry("900x700")
        parts = build(root, order)
        settle(root)
        print(f"=== order={order}")
        for width, height in [(900, 700), (700, 500), (600, 400)]:
            root.geometry(f"{width}x{height}")
            settle(root)
            geoms = [p.winfo_geometry() for p in parts]
            print(f"   {width}x{height}: " + "  ".join(geoms))
        root.destroy()


if __name__ == "__main__":
    main()
