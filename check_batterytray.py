"""Checks what BatteryTray can see on this machine.

The script prints the answer of every driver, so that a machine where
nothing is shown can be examined. Run it with the same account that
starts BatteryTray.

    python check_batterytray.py
"""

from __future__ import annotations

import datetime
import sys
import traceback

try:
    from batterytray.app import collect_devices
    from batterytray.config import Config
    from batterytray.drivers import (bluetooth, hidvendor, hidsupport,
                                      logitech, razer, vendor2, xbox)
except ImportError:
    print("找不到 batterytray 模块，请在这个项目的文件夹里运行本脚本。")
    raise SystemExit(1)


def line(title: str) -> None:
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def show_drivers() -> None:
    """Asks every driver on its own what it can see."""
    for name, read in (("razer", razer.read_devices),
                       ("logitech", logitech.read_devices),
                       ("hidvendor", hidvendor.read_devices),
                       ("vendor2", vendor2.read_devices),
                       ("xbox", xbox.read_devices),
                       ("bluetooth", bluetooth.read_devices)):
        try:
            found = read()
        except Exception:
            print(f"  {name:12} 失败:")
            traceback.print_exc()
            continue
        print(f"  {name:12} {len(found)} 个设备")
        for device in found:
            percent = getattr(device, "percent", None)
            print(f"      {device.name}  电量={percent}")


def show_bluetooth() -> None:
    """Shows what the Bluetooth stack knows."""
    print("  蓝牙无线电回答的设备:")
    radio = bluetooth._radio_connected_addresses()
    if not radio:
        print("      （没有设备。蓝牙无线电可能没有开，"
              "或者设备没有连上）")
    for number, (connected, name) in radio.items():
        print(f"      0x{number:08X} connected={connected} {name}")

    print()
    print("  蓝牙设备节点:")
    for device in bluetooth.read_devices():
        print(f"      {device.name}")
        print(f"          类型={device.kind} 电量={device.percent} "
              f"连接={device.connected}")
        if device.last_report:
            print(f"          电池上报={device.last_report}")
        if device.last_seen:
            print(f"          最后活动={device.last_seen}")


def show_hid() -> None:
    """Shows what the HID subsystem answers."""
    devices = hidsupport.enumerate_interfaces()
    print(f"  HID 接口数: {len(devices)}")
    if not devices:
        print("      （没有接口。HID 子系统可能拒绝了访问，"
              "或者没有接任何 HID 设备）")
    for device in devices[:20]:
        print(f"      vid=0x{device.get('vendor_id', 0):04X} "
              f"pid=0x{device.get('product_id', 0):04X} "
              f"{device.get('product_string')!r}")


def main() -> int:
    print(f"BatteryTray 诊断  {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")

    line("1. 每个驱动读到了什么")
    show_drivers()

    line("2. HID 子系统")
    show_hid()

    line("3. 蓝牙栈")
    show_bluetooth()

    line("4. 应用最终显示的设备")
    devices, failures = collect_devices(Config())
    if not devices:
        print("  没有设备。")
    for device in devices:
        print(f"  {device.name}  电量={device.percent} "
              f"连接={device.connected} 类型={device.kind}")
    if failures:
        print()
        print("  失败的驱动:")
        for failure in failures:
            print(f"      {failure}")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
