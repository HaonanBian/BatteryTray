"""Renders the update window in its states.

The window has to look right when it is still checking, when it found a
new release, when the download runs and when the check failed.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batterytray.dpi import set_dpi_aware  # noqa: E402

set_dpi_aware()

import tkinter as tk  # noqa: E402

from batterytray.update import Release  # noqa: E402
from batterytray.updatedialog import UpdateDialog  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "out_test"


def settle(root, rounds=25):
    """Lets Tk finish the layout."""
    for _ in range(rounds):
        root.update_idletasks()
        root.update()
        time.sleep(0.01)


def shot(dialog, name):
    """Saves a screenshot of the dialog."""
    from PIL import ImageGrab
    x, y = dialog.winfo_rootx(), dialog.winfo_rooty()
    w, h = dialog.winfo_width(), dialog.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(OUT / name)
    print("saved", name)


def main() -> None:
    """Renders the states."""
    OUT.mkdir(exist_ok=True)
    root = tk.Tk()
    root.withdraw()
    family = "Microsoft YaHei UI"

    # ---- The state while the check is running ----
    dialog = UpdateDialog(root, family, 144.0)
    settle(root)
    shot(dialog, "update_checking.png")
    dialog.destroy()

    # ---- The state when a new release was found ----
    dialog = UpdateDialog(root, family, 144.0)
    dialog.show_new_version(Release(
        version="v1.3.0",
        url="https://github.com/HaonanBian/BatteryTray/releases/tag/v1.3.0",
        notes=("本次更新\n\n"
               "· 新增了 AULA 与 Compx 键盘的协议适配\n"
               "· 支持 ASUS ROG 键盘与 Omni 接收器\n"
               "· 修复了窗口缩小时底部按钮消失的问题"),
        asset_name="BatteryTray-1.3.0-portable.zip",
        asset_url="https://example.invalid/portable.zip",
        setup_name="BatteryTray-Setup-1.3.0.exe",
        setup_url="https://example.invalid/setup.exe",
    ))
    settle(root)
    shot(dialog, "update_found.png")
    dialog.destroy()

    # ---- The state while the download runs ----
    dialog = UpdateDialog(root, family, 144.0,
                           on_install=lambda *a: None)
    dialog.show_new_version(Release(
        version="v1.3.0",
        url="https://example.invalid",
        notes="修复了若干问题",
        asset_url="https://example.invalid/portable.zip",
        setup_url="https://example.invalid/setup.exe",
    ))
    settle(root)
    dialog._install()
    dialog._on_progress(45, 100)
    settle(root)
    shot(dialog, "update_installing.png")
    dialog.destroy()

    # ---- The state when the download is tried again ----
    dialog = UpdateDialog(root, family, 144.0,
                           on_install=lambda *a: None)
    dialog.show_new_version(Release(
        version="v1.3.0",
        url="https://example.invalid",
        notes="修复了若干问题",
        asset_url="https://example.invalid/portable.zip",
        setup_url="https://example.invalid/setup.exe",
    ))
    settle(root)
    dialog._install()
    dialog._on_retry(1, "文件不完整")
    settle(root)
    print("retry title:", dialog.title_label.cget("text"))
    print("retry message:", dialog.message_label.cget("text"))
    shot(dialog, "update_retry.png")
    dialog.destroy()

    # ---- The state when the check failed ----
    dialog = UpdateDialog(root, family, 144.0)
    dialog.show_failed("连不上 GitHub：网络超时")
    settle(root)
    shot(dialog, "update_failed.png")
    dialog.destroy()

    # ---- The state when there is no newer version ----
    dialog = UpdateDialog(root, family, 144.0)
    dialog.show_up_to_date()
    settle(root)
    shot(dialog, "update_current.png")
    dialog.destroy()

    root.destroy()


if __name__ == "__main__":
    main()
