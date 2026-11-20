"""A minimal reproduction of the footer that stops following the window.

The main window packs a header, a list and a footer. This script copies
that structure as closely as possible and reports which manager owns each
part, so it can be seen when the footer stops being arranged.
"""

from __future__ import annotations

import tkinter as tk


def build(root: tk.Tk, with_propagate: bool, with_dividers: bool):
    """Builds a copy of the layout of the main window."""
    header = tk.Frame(root, bg="red", height=58)
    header.pack(fill="x", side="top")
    if with_propagate:
        header.pack_propagate(False)

    if with_dividers:
        tk.Frame(root, bg="white", height=1).pack(fill="x", side="top")

    list_wrap = tk.Frame(root, bg="blue")
    list_wrap.pack(fill="both", expand=True)

    if with_dividers:
        tk.Frame(root, bg="white", height=1).pack(fill="x", side="bottom")

    footer = tk.Frame(root, bg="green", height=42)
    footer.pack(fill="x", side="bottom")
    if with_propagate:
        footer.pack_propagate(False)

    tk.Button(footer, text="设置").pack(side="right")
    return header, list_wrap, footer


def settle(root, rounds=30):
    """Lets Tk finish the layout."""
    for _ in range(rounds):
        root.update_idletasks()
        root.update()


def report(root, parts, label):
    """Prints the geometry of every part."""
    print(f"  {label}")
    for name, widget in zip(("header", "list", "footer"), parts):
        print(f"    {name:7s} manager={widget.winfo_manager():6s} "
              f"y={widget.winfo_y():4d} h={widget.winfo_height():4d} "
              f"w={widget.winfo_width():4d} "
              f"req={widget.winfo_reqheight():4d}")


def main() -> None:
    """Runs the reproduction for a few variants."""
    for with_propagate in (False, True):
        for with_dividers in (False, True):
            root = tk.Tk()
            root.geometry("900x700")
            parts = build(root, with_propagate, with_dividers)
            settle(root)
            print(f"=== propagate={with_propagate} dividers={with_dividers}")
            report(root, parts, "at 900x700")
            root.geometry("700x500")
            settle(root)
            report(root, parts, "at 700x500")
            root.destroy()


if __name__ == "__main__":
    main()
