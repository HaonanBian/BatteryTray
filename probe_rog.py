"""Probes a ROG Keris Wireless Aimpoint over USB HID.

The mouse has to be plugged in with a cable, or through the ROG Omni
receiver. Over Bluetooth only the battery level can be read; every
setting command needs the USB control interface.

Run with: .venv/Scripts/python probe_rog.py
"""

from __future__ import annotations

import sys
import time

import hid

ASUS_VID = 0x0B05

# The product id of the mouse depends on how it is connected.
KNOWN_PRODUCTS = {
    0x1A66: "有线（USB 线）",
    0x1A68: "2.4G 接收器直连",
    0x1A6A: "蓝牙",
    0x1ACE: "ROG Omni 接收器",
}

# The ASUS HID protocol.
#
# The packet is 64 bytes. The first byte is the report id, the second one
# the command family and the third one the sub command.
REPORT_READ = 0x12
REPORT_WRITE = 0x51
REPORT_PROFILE = 0x50

SUB_BATTERY = 0x07
SUB_DEVICE_INFO = 0x00
SUB_SETTING = 0x04
SUB_DPI_XY = 0x02
SUB_BUTTONS = 0x05

PACKET_SIZE = 64

# The button slots, in the order the mouse reports them.
SLOT_NAMES = (
    "左键", "右键", "滚轮中键", "后退键", "前进键", "DPI 键", "滚轮上", "滚轮下",
)


def describe(devices: list[dict]) -> list[dict]:
    """Prints every ASUS HID device and marks the likely control ones."""
    print("=== ASUS USB HID 设备 ===")
    mice: list[dict] = []
    for d in devices:
        pid = d["product_id"]
        mode = KNOWN_PRODUCTS.get(pid, "未知")
        marker = ""
        # The control interface uses a vendor usage page.
        if d.get("usage_page") == 0xFF01:
            marker = "  <-- 控制接口"
            mice.append(d)
        print(f"  pid={pid:04X} ({mode}) "
              f"usage_page={d.get('usage_page')} usage={d.get('usage')} "
              f"{d.get('product_string')}{marker}")
    return mice


def build(report_id: int, family: int, *args: int) -> bytes:
    """Builds one protocol packet."""
    packet = bytearray(PACKET_SIZE)
    packet[0] = report_id
    packet[1] = family
    for i, value in enumerate(args):
        packet[2 + i] = value
    return bytes(packet)


def exchange(handle, packet: bytes, label: str) -> bytes | None:
    """Sends a packet and reads the answer."""
    try:
        handle.write(packet)
    except OSError as exc:
        print(f"  写入失败：{exc}")
        return None

    for _ in range(20):
        time.sleep(0.02)
        try:
            answer = handle.read(PACKET_SIZE, timeout_ms=50)
        except OSError as exc:
            print(f"  读取失败：{exc}")
            return None
        if not answer:
            continue
        if answer[0] == 0xFF and answer[1] == 0xAA:
            print(f"  {label}: 设备回了 FF AA —— 这个固件不支持该命令")
            return None
        if len(answer) < 3:
            continue
        return bytes(answer)

    print(f"  {label}: 没有回复")
    return None


def dump(label: str, answer: bytes | None) -> None:
    """Prints a short hex dump of an answer."""
    if answer is None:
        return
    shown = " ".join(f"{b:02X}" for b in answer[:32])
    print(f"  {label}: {shown}")


def probe(handle, report_id: int, name: str) -> None:
    """Runs the read commands that work without writing anything."""
    print()
    print(f"=== {name} (report id 0x{report_id:02X}) ===")

    print("[电量]")
    answer = exchange(handle, build(report_id, REPORT_READ, SUB_BATTERY), "电量")
    dump("回包", answer)
    if answer and answer[1] == REPORT_READ and answer[2] == SUB_BATTERY:
        print(f"  电量 = {answer[5]}%   充电中 = {answer[10] > 0}")

    print("[设备信息 / 配置文件]")
    answer = exchange(handle, build(report_id, REPORT_READ, SUB_DEVICE_INFO),
                      "设备信息")
    dump("回包", answer)
    if answer and len(answer) > 12:
        print(f"  活动配置文件 = {answer[11]}   活动 DPI 档 = {answer[12]}")

    print("[DPI 与回报率]")
    answer = exchange(handle, build(report_id, REPORT_READ, SUB_SETTING, 0x00),
                      "轮询率")
    dump("回包", answer)
    if answer and answer[1] == REPORT_READ and answer[2] == SUB_SETTING:
        print(f"  回报率原始值 = 0x{answer[13]:02X}")
        print(f"  角度吸附 = {answer[17] == 1}")

    print("[DPI 挡位（XY）]")
    answer = exchange(handle, build(report_id, REPORT_READ, SUB_SETTING,
                                    SUB_DPI_XY), "DPI")
    dump("回包", answer)
    if answer and answer[1] == REPORT_READ and answer[2] == SUB_SETTING:
        # HasXYDPI is true for the Aimpoint, so every stage takes four
        # bytes: two for x and two for y. Both are little endian.
        for i in range(4):
            offset = 5 + i * 4
            if offset + 3 >= len(answer):
                break
            x = answer[offset] | (answer[offset + 1] << 8)
            y = answer[offset + 2] | (answer[offset + 3] << 8)
            # encoded * 50 + 50
            print(f"  挡位 {i + 1}: X = {x * 50 + 50}   Y = {y * 50 + 50}")

    print("[按键映射]")
    answer = exchange(handle, build(report_id, REPORT_READ, SUB_BUTTONS,
                                    0x00, 0x00, 0x00), "按键")
    dump("回包", answer)
    if answer and answer[1] == REPORT_READ and answer[2] == SUB_BUTTONS:
        print(f"  完整回包（{len(answer)} 字节）:")
        for row in range(0, min(len(answer), 64), 16):
            chunk = answer[row:row + 16]
            print("    " + " ".join(f"{b:02X}" for b in chunk))
        # The answer holds one two byte action code per slot, starting at
        # offset five. The bytes are little endian.
        print("  各挡位当前操作:")
        for slot, name in enumerate(SLOT_NAMES):
            offset = 5 + slot * 2
            if offset + 1 >= len(answer):
                break
            code = answer[offset] | (answer[offset + 1] << 8)
            print(f"    {name:10s} = 0x{code:04X}")


def main() -> int:
    devices = [d for d in hid.enumerate(ASUS_VID, 0)
               if d["vendor_id"] == ASUS_VID]
    if not devices:
        print("没有找到任何 ASUS (0x0B05) 的 USB HID 设备。")
        print("鼠标需要插 USB 线，或者插 ROG Omni 接收器。")
        return 1

    mice = describe(devices)

    # The report id depends on the connection: 0x03 for the Omni
    # receiver, 0x00 for a direct cable connection.
    report_ids = {0x1ACE: 0x03}
    for d in mice:
        pid = d["product_id"]
        report_id = report_ids.get(pid, 0x00)
        mode = KNOWN_PRODUCTS.get(pid, "未知")
        print()
        print(f"### 打开控制接口 pid={pid:04X} ({mode}) ###")
        try:
            handle = hid.device()
            handle.open_path(d["path"])
        except OSError as exc:
            print(f"  打开失败：{exc}")
            continue
        try:
            probe(handle, report_id, mode)
        finally:
            handle.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
