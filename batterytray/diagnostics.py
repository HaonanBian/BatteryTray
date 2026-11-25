"""Builds a report of what BatteryTray can see on this machine.

A user whose devices do not show up cannot tell what went wrong. The
report answers that question: it asks every driver on its own, asks the
HID subsystem and the Bluetooth radio, and writes down what came back
together with the reason for every failure.

The report is plain text, so that it can be pasted into a chat, put into
an issue or saved next to the program.
"""

from __future__ import annotations

import datetime
import platform
import re
import sys
import traceback

from . import __version__
from .config import Config
from .drivers import bluetooth, hidsupport, hidvendor, logitech, razer
from .drivers import vendor2, xbox

# The drivers that are asked, in the order they are asked.
DRIVERS = (
    ("razer", razer.read_devices),
    ("logitech", logitech.read_devices),
    ("hidvendor", hidvendor.read_devices),
    ("vendor2", vendor2.read_devices),
    ("xbox", xbox.read_devices),
    ("bluetooth", bluetooth.read_devices),
)


def _section(title: str) -> list[str]:
    """The heading of a part of the report."""
    return ["", "=" * 60, title, "=" * 60]


def _driver_lines() -> list[str]:
    """Asks every driver on its own what it can see."""
    lines: list[str] = []
    for name, read in DRIVERS:
        try:
            found = read()
        except Exception:
            lines.append(f"  {name:<12} 失败:")
            lines.append("    " + traceback.format_exc().replace(
                "\n", "\n    "))
            continue
        lines.append(f"  {name:<12} {len(found)} 个设备")
        for device in found:
            percent = getattr(device, "percent", None)
            connected = getattr(device, "connected", None)
            lines.append(f"      {device.name}  电量={percent}  "
                         f"连接={connected}")
    return lines


def _hid_lines() -> list[str]:
    """Shows what the HID subsystem answers.

    The usage page, the usage and the collection of an interface are what
    tell a 2.4 GHz dongle apart from the device behind it. A report that
    only says "Dongle 2.4G" cannot be acted on: there is no way to tell
    which protocol the dongle speaks.
    """
    lines: list[str] = []
    before = hidsupport.failure_count()
    devices = hidsupport.enumerate_interfaces()
    lines.append(f"  HID 接口数: {len(devices)}")
    if not devices:
        lines.append("      （没有接口。HID 子系统可能拒绝了访问，"
                     "或者没有接任何 HID 设备）")
    if hidsupport.failure_count() > before:
        lines.append(f"      HID 子系统报错: {hidsupport.last_error()}")
    for device in devices:
        lines.append(
            f"      vid=0x{device.get('vendor_id', 0):04X} "
            f"pid=0x{device.get('product_id', 0):04X} "
            f"usage_page=0x{device.get('usage_page', 0):04X} "
            f"usage=0x{device.get('usage', 0):04X} "
            f"{device.get('product_string')!r}")
        collection = _collection_text(device.get("path", ""))
        if collection:
            lines.append(f"          接口={collection}")
    return lines


# The part of a HID path that names the interface and the collection.
_COLLECTION = re.compile(r"mi_\d+(?:&col\d+)?", re.IGNORECASE)


def _collection_text(path: bytes | str) -> str:
    """The interface and collection a HID path points at, e.g. ``mi_02&col03``.

    A receiver with two collections looks the same in the vendor and
    product id; only this part tells which one carries the answers.
    """
    if isinstance(path, bytes):
        path = path.decode("utf-8", errors="replace")
    match = _COLLECTION.search(path)
    return match.group(0) if match else ""


def _local_time(stamp: datetime.datetime | None) -> str:
    """Shows a stamp in the local time of the machine.

    The Bluetooth stamps are read in UTC, which is right for comparing
    them but unreadable in a report: a report taken at nine in the
    evening showed "13:18" and looked hours old.
    """
    if stamp is None:
        return ""
    return stamp.replace(tzinfo=datetime.UTC).astimezone().strftime(
        "%Y-%m-%d %H:%M:%S")


def _bluetooth_lines() -> list[str]:
    """Shows what the Bluetooth stack knows."""
    lines: list[str] = []
    lines.append("  蓝牙无线电回答的设备:")
    try:
        radio = bluetooth._radio_connected_addresses()
    except Exception as error:
        radio = {}
        lines.append(f"      查询失败: {error}")
    if radio:
        for number, (connected, name) in radio.items():
            lines.append(f"      0x{number:08X} connected={connected} {name}")
    else:
        lines.append("      （没有设备。蓝牙无线电可能没有开，"
                     "或者设备没有连上）")

    lines.append("")
    lines.append("  蓝牙设备节点:")
    try:
        nodes = bluetooth.read_devices()
    except Exception as error:
        nodes = []
        lines.append(f"      查询失败: {error}")
    for device in nodes:
        lines.append(f"      {device.name}")
        lines.append(f"          类型={device.kind} "
                     f"电量={device.percent} 连接={device.connected}")
        if device.last_report:
            lines.append(f"          电池上报={_local_time(device.last_report)}")
        if device.last_seen:
            lines.append(f"          最后活动={_local_time(device.last_seen)}")
        # The stamps of the registry only change when the link is set up,
        # so they are shown as evidence and not as the truth.
        if device.registry_connected:
            lines.append(f"          注册表连接="
                         f"{_local_time(device.registry_connected)}")
        if device.registry_seen:
            lines.append(f"          注册表见过="
                         f"{_local_time(device.registry_seen)}")
    return lines


def _result_lines() -> list[str]:
    """Shows what the app finally puts on the screen."""
    from .app import collect_devices

    lines: list[str] = []
    try:
        devices, failures = collect_devices(Config())
    except Exception:
        lines.append("  收集设备时出错:")
        lines.append("    " + traceback.format_exc().replace("\n", "\n    "))
        return lines

    if not devices:
        lines.append("  没有设备。")
    for device in devices:
        lines.append(f"  {device.name}  电量={device.percent} "
                     f"连接={device.connected} 类型={device.kind}")
    if failures:
        lines.append("")
        lines.append("  失败的驱动:")
        for failure in failures:
            lines.append(f"      {failure}")
    return lines


def _system_lines() -> list[str]:
    """Says what machine the report comes from."""
    lines = [
        f"  程序版本: {__version__}",
        f"  Python:   {sys.version.split()[0]}",
        f"  系统:     {platform.system()} {platform.release()}",
        f"  机器:     {platform.machine()}",
        f"  时区:     {_timezone_name()}",
    ]
    return lines


def _timezone_name() -> str:
    """The name of the time zone and its offset."""
    now = datetime.datetime.now().astimezone()
    offset = now.utcoffset()
    seconds = int(offset.total_seconds()) if offset else 0
    sign = "+" if seconds >= 0 else "-"
    hours, rest = divmod(abs(seconds), 3600)
    minutes = rest // 60
    name = now.tzname() or "本地时间"
    return f"{name} (UTC{sign}{hours:02d}:{minutes:02d})"


def build_report() -> str:
    """Builds the whole report as one piece of text."""
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = [f"BatteryTray 诊断报告  {stamp}"]
    lines += _section("0. 这台机器")
    lines += _system_lines()
    lines += _section("1. 每个驱动读到了什么")
    lines += _driver_lines()
    lines += _section("2. HID 子系统")
    lines += _hid_lines()
    lines += _section("3. 蓝牙栈")
    lines += _bluetooth_lines()
    lines += _section("4. 应用最终显示的设备")
    lines += _result_lines()
    lines.append("")
    return "\n".join(lines)
