"""Copies the layout of the main window and removes one piece at a time.

The footer of the main window stops following the window when it becomes
smaller. This script rebuilds the same layout piece by piece, so the part
that causes it can be found.
"""

from __future__ import annotations

import tkinter as tk


def settle(root, rounds=30):
    """Lets Tk finish the layout."""
    for _ in range(rounds):
        root.update_idletasks()
        root.update()


def build(root, use_canvas=True, use_expand=True, footer_first=False):
    """Builds a copy of the layout of the main window."""
    header = tk.Frame(root, bg="red", height=58)
    header.pack(fill="x", side="top")
    header.pack_propagate(False)
    tk.Frame(root, bg="white", height=1).pack(fill="x", side="top")

    def build_list(parent):
        """The scrollable list, exactly as the window has it."""
        list_wrap = tk.Frame(parent, bg="blue")
        if use_expand:
            list_wrap.pack(fill="both", expand=True)
        else:
            list_wrap.pack(fill="both")
        if not use_canvas:
            tk.Frame(list_wrap, bg="cyan", height=200).grid(
                row=0, column=0, sticky="nsew")
            list_wrap.grid_columnconfigure(0, weight=1)
            return list_wrap
        canvas = tk.Canvas(list_wrap, bg="blue", highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(list_wrap, orient="vertical",
                                  command=canvas.yview, width=10)
        canvas.configure(yscrollcommand=scrollbar.set)
        list_wrap.grid_columnconfigure(0, weight=1)
        list_wrap.grid_rowconfigure(0, weight=1)
        canvas.grid(row=0, column=0, sticky="nsew", padx=(14, 8), pady=(12, 0))
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=(12, 0))
        inner = tk.Frame(canvas, bg="cyan", height=200)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        return list_wrap

    def build_footer():
        """The footer with the two buttons."""
        tk.Frame(root, bg="white", height=1).pack(fill="x", side="bottom")
        footer = tk.Frame(root, bg="green", height=42)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        tk.Canvas(footer, bg="green", width=60, height=30).pack(side="right")
        tk.Canvas(footer, bg="green", width=60, height=30).pack(side="right")
        return footer

    if footer_first:
        build_footer()
        build_list(root)
    else:
        build_list(root)
        build_footer()
    return header


def report(root, footer, label):
    """Prints where the footer ended up."""
    print(f"  {label}: window={root.winfo_width()}x{root.winfo_height()} "
          f"footer geo={footer.winfo_geometry()}")


def main() -> None:
    """Runs the variants."""
    for use_canvas in (True, False):
        for footer_first in (False, True):
            root = tk.Tk()
            root.geometry("900x700")
            header = build(root, use_canvas=use_canvas,
                           footer_first=footer_first)
            settle(root)
            footer = [c for c in root.winfo_children()
                      if c.winfo_class() == "Frame"][-1]
            print(f"=== canvas={use_canvas} footer_first={footer_first}")
            report(root, footer, "900x700")
            root.geometry("700x500")
            settle(root)
            report(root, footer, "700x500")
            root.destroy()


if __name__ == "__main__":
    main()
