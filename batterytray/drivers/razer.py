"""Razer HID battery driver.

Reads battery level and charging state directly from Razer wireless devices over
HID feature reports, without Synapse and without a kernel driver.

Protocol mirrors OpenRazer's ``struct razer_report`` (driver/razercommon.h):

    offset  field
    0       status (0x00 new, 0x01 busy, 0x02 success)
    1       transaction id
    2-3     remaining packets
    4       protocol type
    5       data size
    6       command class
    7       command id
    8..87   arguments (80 bytes)
    88      crc (XOR of bytes 2..87)
    89      reserved

On the wire the buffer carries a leading HID report id, so a feature report is
91 bytes and every field above is shifted by one.

References:
    openrazer/openrazer            - driver/razercommon.h, razerchromacommon.c
    damianyoko/viper-tray          - Windows port of the same query
    nuxencs/razertray              - cleaner report struct + CRC unit tests
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time
from dataclasses import dataclass
from enum import IntEnum

import hid

# Razer USB vendor id.
RAZER_VID = 0x1532

# HID usage page "Generic Desktop".
USAGE_PAGE_GENERIC_DESKTOP = 0x01
# HID usage "Mouse".
USAGE_MOUSE = 0x02

# ``struct razer_report`` is 90 bytes; the feature report adds a report id.
REPORT_LENGTH = 90
FEATURE_REPORT_LENGTH = REPORT_LENGTH + 1

# Device ids that answer the battery query, mapped to their transaction id.
# Transaction ids come from OpenRazer's per-device definitions.
# Auto-generated from nuxencs/razertray device_map.rs (OpenRazer device database).
# pid -> (name, transaction_id, supports_charging_status)
RAZER_DEVICES: dict[int, tuple[str, int, bool]] = {
    0x001F: ('Razer Naga Epic', 0xFF, True),
    0x0024: ('Razer Mamba 2012 Wired', 0xFF, True),
    0x0025: ('Razer Mamba 2012 Wireless', 0xFF, True),
    0x0032: ('Razer Ouroboros', 0xFF, True),
    0x003E: ('Razer Naga Epic Chroma', 0xFF, True),
    0x003F: ('Razer Naga Epic Chroma Dock', 0xFF, True),
    0x0044: ('Razer Mamba Wired', 0xFF, True),
    0x0045: ('Razer Mamba Wireless', 0xFF, True),
    0x0059: ('Razer Lancehead Wired', 0x3F, True),
    0x005A: ('Razer Lancehead Wireless', 0x3F, True),
    0x0062: ('Razer Atheris Receiver', 0x1F, False),
    0x006F: ('Razer Lancehead Wireless Receiver', 0x1F, True),
    0x0070: ('Razer Lancehead Wireless Wired', 0x1F, True),
    0x0072: ('Razer Mamba Wireless Receiver', 0x3F, True),
    0x0073: ('Razer Mamba Wireless Wired', 0x3F, True),
    0x0077: ('Razer Pro Click Receiver', 0x1F, True),
    0x007A: ('Razer Viper Ultimate Wired', 0xFF, True),
    0x007B: ('Razer Viper Ultimate Wireless', 0xFF, True),
    0x007C: ('Razer Deathadder V2 Pro Wired', 0x3F, True),
    0x007D: ('Razer Deathadder V2 Pro Wireless', 0x3F, True),
    0x0080: ('Razer Pro Click Wired', 0x1F, True),
    0x0083: ('Razer Basilisk X Hyperspeed', 0xFF, False),
    0x0086: ('Razer Basilisk Ultimate Wired', 0x1F, True),
    0x0088: ('Razer Basilisk Ultimate Receiver', 0x1F, True),
    0x008F: ('Razer Naga Pro Wired', 0x1F, True),
    0x0090: ('Razer Naga Pro Wireless', 0x1F, True),
    0x0094: ('Razer Orochi V2 Receiver', 0x1F, False),
    0x0095: ('Razer Orochi V2 Bluetooth', 0x1F, False),
    0x009A: ('Razer Pro Click Mini Receiver', 0x1F, True),
    0x009C: ('Razer Deathadder V2 X Hyperspeed', 0x1F, False),
    0x009E: ('Razer Viper Mini Se Wired', 0x1F, True),
    0x009F: ('Razer Viper Mini Se Wireless', 0x1F, True),
    0x00A5: ('Razer Viper V2 Pro Wired', 0x1F, True),
    0x00A6: ('Razer Viper V2 Pro Wireless', 0x1F, True),
    0x00A7: ('Razer Naga V2 Pro Wired', 0x1F, True),
    0x00A8: ('Razer Naga V2 Pro Wireless', 0x1F, True),
    0x00AA: ('Razer Basilisk V3 Pro Wired', 0x1F, True),
    0x00AB: ('Razer Basilisk V3 Pro Wireless', 0x1F, True),
    0x00AF: ('Razer Cobra Pro Wired', 0x1F, True),
    0x00B0: ('Razer Cobra Pro Wireless', 0x1F, True),
    0x00B3: ('Razer Hyperpolling Wireless Dongle', 0x1F, True),
    0x00B4: ('Razer Naga V2 Hyperspeed Receiver', 0x1F, False),
    0x00B6: ('Razer Deathadder V3 Pro Wired', 0x1F, True),
    0x00B7: ('Razer Deathadder V3 Pro Wireless', 0x1F, True),
    0x00B8: ('Razer Viper V3 Hyperspeed', 0x1F, False),
    0x00B9: ('Razer Basilisk V3 X Hyperspeed', 0x1F, False),
    0x00BE: ('Razer Deathadder V4 Pro Wired', 0x1F, True),
    0x00BF: ('Razer Deathadder V4 Pro Wireless', 0x1F, True),
    0x00C0: ('Razer Viper V3 Pro Wired', 0x1F, True),
    0x00C1: ('Razer Viper V3 Pro Wireless', 0x1F, True),
    0x00C2: ('Razer Deathadder V3 Pro Wired Alt', 0x1F, True),
    0x00C3: ('Razer Deathadder V3 Pro Wireless Alt', 0x1F, True),
    0x00C4: ('Razer Deathadder V3 Hyperspeed Wired', 0x1F, True),
    0x00C5: ('Razer Deathadder V3 Hyperspeed Wireless', 0x1F, True),
    0x00C7: ('Razer Pro Click V2 Vertical Edition Wired', 0x1F, True),
    0x00C8: ('Razer Pro Click V2 Vertical Edition Wireless', 0x1F, True),
    0x00CB: ('Razer Basilisk V3 35k', 0x1F, True),
    0x00CC: ('Razer Basilisk V3 Pro 35k Wired', 0x1F, True),
    0x00CD: ('Razer Basilisk V3 Pro 35k Wireless', 0x1F, True),
    0x00D0: ('Razer Pro Click V2 Wired', 0x1F, True),
    0x00D1: ('Razer Pro Click V2 Wireless', 0x1F, True),
    0x00D3: ('Razer Basilisk Mobile Wired', 0x1F, False),
    0x00D4: ('Razer Basilisk Mobile Receiver', 0x1F, False),
    0x00D6: ('Razer Basilisk V3 Pro 35k Phantom Green Edition Wired', 0x1F, True),
    0x00D7: ('Razer Basilisk V3 Pro 35k Phantom Green Edition Wireless', 0x1F, True),
}

# Transaction ids to try for devices missing from the map above.
PROBE_TRANSACTION_IDS = (0x1F, 0x3F, 0xFF)

# Command class 0x07 is the "power" class in OpenRazer.
CMD_CLASS_POWER = 0x07
# Command 0x80 reads the raw battery level (0..255).
CMD_BATTERY_LEVEL = 0x80
# Command 0x84 reads the charging status (non-zero while charging).
CMD_CHARGING_STATUS = 0x84


class Status(IntEnum):
    """Report status byte, matching OpenRazer's ``RAZER_CMD_*``."""

    NEW = 0x00
    BUSY = 0x01
    SUCCESSFUL = 0x02
    FAILURE = 0x03
    TIMEOUT = 0x04
    NOT_SUPPORTED = 0x05


def _build_request(transaction_id: int, command_class: int, command_id: int) -> bytes:
    """Builds a Razer feature report request with a valid CRC."""
    buf = bytearray(FEATURE_REPORT_LENGTH)
    buf[1] = Status.NEW
    buf[2] = transaction_id
    buf[6] = 0x02          # data size
    buf[7] = command_class
    buf[8] = command_id
    crc = 0
    for i in range(3, 89):
        crc ^= buf[i]
    buf[89] = crc
    return bytes(buf)


def _parse_report(data: bytes) -> tuple[Status, int, int]:
    """Splits a raw feature report into ``(status, command_class, command_id)``."""
    # data[0] is the HID report id, the Razer report follows from index 1.
    status = Status(data[1]) if data[1] in Status._value2member_map_ else Status.FAILURE
    return status, data[7], data[8]


def _crc_valid(data: bytes) -> bool:
    """Checks the CRC the device echoed back."""
    crc = 0
    for i in range(3, 89):
        crc ^= data[i]
    return crc == data[89]


class _HidHandle:
    """Opens a HID path with ``desired_access=0``.

    Windows' ``mouclass`` driver holds an exclusive lock on mice while they are
    in use, so a read/write open fails with ``ERROR_ACCESS_DENIED``. A
    zero-access handle is enough for feature reports, which is how both
    ``damianyoko/viper-tray`` and the Win32 code in ``nuxencs/razertray``
    work around it.
    """

    def __init__(self, path: str):
        self._handle = None
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._hid = ctypes.WinDLL("hid.dll", use_last_error=True)

        # Without an explicit restype the returned handle is truncated to a
        # 32-bit int, which breaks on 64-bit Windows.
        self._kernel32.CreateFileW.restype = wt.HANDLE
        self._kernel32.CreateFileW.argtypes = [
            ctypes.c_wchar_p, wt.DWORD, wt.DWORD, ctypes.c_void_p,
            wt.DWORD, wt.DWORD, wt.HANDLE]
        self._kernel32.CloseHandle.argtypes = [wt.HANDLE]
        self._kernel32.CloseHandle.restype = wt.BOOL
        self._hid.HidD_SetFeature.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD]
        self._hid.HidD_SetFeature.restype = wt.BOOL
        self._hid.HidD_GetFeature.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD]
        self._hid.HidD_GetFeature.restype = wt.BOOL

        handle = self._kernel32.CreateFileW(
            ctypes.c_wchar_p(path),
            0,                                     # desired access
            0x1 | 0x2,                             # FILE_SHARE_READ | FILE_SHARE_WRITE
            None,
            3,                                     # OPEN_EXISTING
            0x80,                                  # FILE_ATTRIBUTE_NORMAL
            None,
        )
        invalid = ctypes.c_void_p(-1).value
        if handle == invalid or handle is None:
            raise OSError(ctypes.get_last_error(), "CreateFileW failed")
        self._handle = handle

    def set_feature(self, data: bytes) -> bool:
        return bool(self._hid.HidD_SetFeature(self._handle, ctypes.c_char_p(data), len(data)))

    def get_feature(self, length: int) -> bytes | None:
        buf = ctypes.create_string_buffer(length)
        if not self._hid.HidD_GetFeature(self._handle, buf, length):
            return None
        return buf.raw

    def close(self) -> None:
        if self._handle is not None:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self) -> "_HidHandle":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _query(handle: _HidHandle, transaction_id: int, command_class: int,
           command_id: int, retries: tuple[int, ...] = (80, 150, 250, 500)) -> bytes | None:
    """Sends one command and returns the raw response, or ``None`` on failure.

    The dongle needs time to complete its 2.4 GHz round trip to the mouse, so
    each attempt waits longer than the last. Only ``status == 0x02`` counts as
    success; ``0x01`` means busy and triggers another attempt.
    """
    request = _build_request(transaction_id, command_class, command_id)
    for sleep_ms in retries:
        if not handle.set_feature(request):
            return None
        time.sleep(sleep_ms / 1000)
        response = handle.get_feature(FEATURE_REPORT_LENGTH)
        if response is None or len(response) < FEATURE_REPORT_LENGTH:
            continue
        status, _, _ = _parse_report(response)
        if status == Status.SUCCESSFUL:
            return response
        if status != Status.BUSY:
            return None
    return None


@dataclass(frozen=True)
class RazerDevice:
    """A Razer device that reported a battery level."""

    name: str
    product_id: int
    percent: int
    charging: bool
    connection: str = ""


def _device_name(product_id: int, product_string: str) -> str:
    known = RAZER_DEVICES.get(product_id)
    if known:
        return known[0]
    if product_string:
        return product_string
    return f"Razer Device {product_id:04X}"


def _supports_charging(product_id: int) -> bool:
    """Whether the device answers the charging-status command."""
    known = RAZER_DEVICES.get(product_id)
    return known[2] if known else True


def _candidate_interfaces() -> list[dict]:
    """Lists HID interfaces that may carry the Razer battery query."""
    candidates = []
    for dev in hid.enumerate(RAZER_VID):
        # The battery query lives on the mouse collection, or on a vendor
        # collection for headsets and other non-mouse peripherals.
        is_mouse = (dev["usage_page"] == USAGE_PAGE_GENERIC_DESKTOP
                    and dev["usage"] == USAGE_MOUSE)
        is_vendor = dev["usage_page"] not in (
            USAGE_PAGE_GENERIC_DESKTOP, 0x12)
        if not (is_mouse or is_vendor):
            continue
        candidates.append(dev)
    # Mouse interface 0 first: that is where OpenRazer sends mouse commands.
    candidates.sort(key=lambda d: (
        0 if (d["usage_page"] == USAGE_PAGE_GENERIC_DESKTOP and d["usage"] == USAGE_MOUSE
              and d["interface_number"] == 0) else
        1 if (d["usage_page"] == USAGE_PAGE_GENERIC_DESKTOP and d["usage"] == USAGE_MOUSE) else 2,
        d["product_id"], d["interface_number"],
    ))
    return candidates


def _transaction_id_for(handle: _HidHandle, product_id: int) -> int | None:
    """Finds the transaction id a device answers to."""
    known = RAZER_DEVICES.get(product_id)
    candidates = [known[1]] if known else list(PROBE_TRANSACTION_IDS)
    for tid in candidates:
        if _query(handle, tid, CMD_CLASS_POWER, CMD_BATTERY_LEVEL, retries=(80, 150)):
            return tid
    return None


def read_devices() -> list[RazerDevice]:
    """Reads battery level from every connected Razer device.

    Returns one entry per device that answered. Devices that are asleep or
    simply absent are skipped.
    """
    found: dict[tuple[int, str], RazerDevice] = {}

    for dev in _candidate_interfaces():
        product_id = dev["product_id"]
        path = dev["path"]
        if isinstance(path, bytes):
            path = path.decode("utf-8", errors="replace")

        try:
            handle = _HidHandle(path)
        except OSError:
            continue

        with handle:
            tid = _transaction_id_for(handle, product_id)
            if tid is None:
                continue

            response = _query(handle, tid, CMD_CLASS_POWER, CMD_BATTERY_LEVEL)
            if response is None:
                continue
            if not _crc_valid(response):
                continue

            raw = response[10]
            if raw == 0:
                # A zero reading usually means the mouse is asleep rather than
                # genuinely empty; skip it so a stale value is not shown.
                continue
            percent = min(100, raw * 100 // 255)

            charging = False
            if _supports_charging(product_id):
                charge_response = _query(handle, tid, CMD_CLASS_POWER, CMD_CHARGING_STATUS)
                if charge_response is not None and _crc_valid(charge_response):
                    charging = charge_response[10] > 0

            product_string = dev.get("product_string") or ""
            name = _device_name(product_id, product_string)
            serial = dev.get("serial_number") or ""
            key = (product_id, serial or name)
            found[key] = RazerDevice(name=name, product_id=product_id,
                                     percent=percent, charging=charging,
                                     connection=_connection_mode(name, charging))

    return sorted(found.values(), key=lambda d: d.name)


def _connection_mode(name: str, charging: bool) -> str:
    """A human-readable connection mode for a Razer mouse.

    Razer exposes a separate USB id for the wired and the wireless variant
    of a mouse, and the device database names them accordingly.
    """
    lowered = name.lower()
    if "wired" in lowered:
        return "有线连接"
    if charging:
        return "充电中（底座）"
    if "wireless" in lowered or "hyperspeed" in lowered:
        return "2.4GHz 无线"
    return "无线连接"
