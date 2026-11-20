"""Checks how Tk's packer divides the window between the three sections.

The main window packs a header, a scrollable list and a footer. This
script measures what each of them gets at several window heights.
"""

from __future__ import annotations

import tkinter as tk


def build(root: tk.Tk, order: str) -> dict:
    """Builds the layout and returns the three frames.

    ``order`` decides the order in which the sections are packed.
    """
    header = tk.Frame(root, bg="red", height=58)
    list_wrap = tk.Frame(root, bg="blue")
    footer = tk.Frame(root, bg="green", height=42)

    if order == "pack-first":
        header.pack(fill="x", side="top")
        list_wrap.pack(fill="both", expand=True)
        footer.pack(fill="x", side="bottom")
    else:
        header.pack(fill="x", side="top")
        list_wrap.pack(fill="both", expand=True)
        footer.pack(fill="x", side="bottom")
    return {"header": header, "list": list_wrap, "footer": footer}


def main() -> None:
    root = tk.Tk()
    root.geometry("400x300")
    frames = build(root, "pack-first")

    for height in (300, 260, 200, 150, 120, 100):
        root.geometry(f"400x{height}")
        root.update_idletasks()
        root.update()
        print(f"window height {height:4d} -> "
              f"header={frames['header'].winfo_height():4d} "
              f"list={frames['list'].winfo_height():4d} "
              f"footer={frames['footer'].winfo_height():4d}")

    root.destroy()


if __name__ == "__main__":
    main()
