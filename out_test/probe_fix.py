"""Checks the repair for the footer of the main window.

The list of devices asks for a lot of room, so the packer pushes the
footer out of the window when the window becomes small. Letting the
list be compressed brings the footer back.
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


def build(root, compress_list: bool):
    """Builds the three sections of the window."""
    header = tk.Frame(root, bg="red", height=87)
    header.pack(fill="x", side="top")
    header.pack_propagate(False)
    tk.Frame(root, bg="white", height=1).pack(fill="x", side="top")

    list_wrap = tk.Frame(root, bg="blue")
    list_wrap.pack(fill="both", expand=True)
    if compress_list:
        # The list may be squeezed, so it stops asking for the room its
        # content needs.
        list_wrap.pack_propagate(False)

    canvas = tk.Canvas(list_wrap, bg="blue", highlightthickness=0, bd=0)
    scrollbar = tk.Scrollbar(list_wrap, orient="vertical",
                              command=canvas.yview, width=10)
    canvas.configure(yscrollcommand=scrollbar.set)
    list_wrap.grid_columnconfigure(0, weight=1)
    list_wrap.grid_rowconfigure(0, weight=1)
    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")

    # The content of the list is tall, just like the cards of the app.
    inner = tk.Frame(canvas, bg="cyan", height=414)
    canvas.create_window((0, 0), window=inner, anchor="nw")

    tk.Frame(root, bg="white", height=1).pack(fill="x", side="bottom")
    footer = tk.Frame(root, bg="green", height=63)
    footer.pack(fill="x", side="bottom")
    footer.pack_propagate(False)
    tk.Button(footer, text="设置").pack(side="right")
    tk.Button(footer, text="刷新").pack(side="right")
    return header, list_wrap, footer


def main() -> None:
    """Runs both variants."""
    for compress_list in (False, True):
        root = tk.Tk()
        root.geometry("900x700")
        parts = build(root, compress_list)
        settle(root)
        print(f"=== compress_list={compress_list}")
        for width, height in [(900, 700), (700, 500), (600, 400),
                              (540, 390), (540, 300)]:
            root.geometry(f"{width}x{height}")
            settle(root)
            geoms = [p.winfo_geometry() for p in parts]
            print(f"   {width}x{height}: " + "  ".join(geoms))
        root.destroy()


if __name__ == "__main__":
    main()
