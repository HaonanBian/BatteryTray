"""Battery levels for Logitech mice and keyboards over HID++ 2.0.

Logitech's wireless peripherals expose a small vendor HID interface and a
feature based protocol called HID++ 2.0. The same interface is used by a
directly connected device and by every device paired to a Unifying/Bolt
receiver; a receiver multiplexes its devices with a device index.

The implementation is intentionally read-only. It borrows the feature
numbers and response layout from Solaar and from the
``2.4G-battery-viewer`` project:

* ``0x1000`` battery status: percentage, next level, charging state
* ``0x1004`` unified battery: percentage and charging state
* ``0x1001`` battery voltage: used when the device has no percentage
* ``0x0005`` device name: used to tell a mouse from a keyboard

References:
    pwr-Solaar/Solaar             - HID++ 2.0 feature documentation
    yszyszysz233/2.4G-battery-viewer - a compact Python implementation
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import hid

from . import hidsupport

LOGITECH_VID = 0x046D
HIDPP_USAGE_PAGE = 0xFF00

# HID++ report ids and their full packet lengths (report id included).
REPORT_LONG = 0x11
REPORT_SHORT = 0x10
LONG_LENGTH = 20
SHORT_LENGTH = 7

# HID++ 2.0 features.
FEATURE_ROOT = 0x0000
FEATURE_DEVICE_NAME = 0x0005
FEATURE_BATTERY_STATUS = 0x1000
FEATURE_BATTERY_VOLTAGE = 0x1001
FEATURE_UNIFIED_BATTERY = 0x1004

# The charging state byte of 0x1000 and 0x1004.
STATUS_DISCHARGING = 0
STATUS_CHARGING = 1
STATUS_CHARGING_NEARLY_FULL = 2
STATUS_FULL = 3
STATUS_CHARGING_SLOW = 4

# A receiver multiplexes several devices. Direct devices use 0xFF, but a
# few older ones use 0x00.
DIRECT_INDICES = (0xFF, 0x00)
RECEIVER_INDICES = (1, 2, 3, 4, 5, 6)

# Voltage to percentage table, used by devices that only implement 0x1001.
_VOLTAGE_CURVE = (
    (4186, 100), (4067, 90), (3989, 80), (3922, 70), (3859, 60),
    (3811, 50), (3778, 40), (3751, 30), (3717, 20), (3671, 10),
    (3646, 5), (3579, 2), (3500, 0),
)

# Names that make the device type obvious. HID++ has no reliable "kind"
# feature for every model, so the name is the best fallback.
_KEYBOARD_WORDS = (
    "keyboard", "keys", "k380", "k400", "k600", "k650", "k780", "k800",
    "k830", "k850", "mx keys", "craft", "g915", "g815", "g715", "g713",
    "g613", "g413", "g513", "g512", "pro x tkl", "pop keys", "pebble keys",
)
_MOUSE_WORDS = (
    "mouse", "mx master", "mx anywhere", "mx vertical", "lift", "ergo",
    "g502", "g304", "g305", "g403", "g604", "g703", "g903", "g pro",
    "m185", "m220", "m330", "m350", "m590", "m720",
)


class LogitechError(Exception):
    """The device did not answer a HID++ request."""


@dataclass(frozen=True)
class LogitechDevice:
    """One wireless Logitech mouse or keyboard that reported a level."""

    name: str
    percent: int
    charging: bool
    kind: str
    connection: str
    product_id: int
    connected: bool = True


def _kind_from_name(name: str) -> str:
    """Guesses mouse or keyboard from a product name."""
    lowered = name.lower()
    if any(word in lowered for word in _KEYBOARD_WORDS):
        return "keyboard"
    if any(word in lowered for word in _MOUSE_WORDS):
        return "mouse"
    return "mouse"


def _connection_from_path(path: str, product_string: str) -> str:
    """Names the transport for the connection column."""
    lowered = path.lower()
    if "bth" in lowered:
        return "蓝牙"
    if "receiver" in product_string.lower():
        return "2.4G 接收器"
    return "USB"


def _voltage_percent(millivolts: int) -> int:
    """Estimates a percentage from a Li-ion voltage.

    This is only a fallback for devices without a percentage feature. It is
    the same piecewise linear curve Solaar uses.
    """
    if millivolts >= _VOLTAGE_CURVE[0][0]:
        return 100
    if millivolts <= _VOLTAGE_CURVE[-1][0]:
        return 0
    for (high_mv, high_pct), (low_mv, low_pct) in zip(
            _VOLTAGE_CURVE, _VOLTAGE_CURVE[1:]):
        if low_mv <= millivolts <= high_mv:
            ratio = (millivolts - low_mv) / (high_mv - low_mv)
            return round(low_pct + (high_pct - low_pct) * ratio)
    return 0


class LogitechHidpp:
    """One HID++ interface, bound to one device index."""

    def __init__(self, path: bytes | str, product_id: int,
                 product_string: str, index: int, report_id: int,
                 packet_length: int):
        self.path = path
        self.product_id = product_id
        self.product_string = product_string
        self.index = index
        self.report_id = report_id
        self.packet_length = packet_length
        self._handle: hid.device | None = None
        try:
            handle = hid.device()
            handle.open_path(path)
        except OSError as exc:
            raise LogitechError(f"无法打开罗技设备：{exc}") from exc
        self._handle = handle

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _call(self, feature_index: int, function: int,
              *params: int) -> bytes | None:
        """Sends one HID++ request and returns the matching response."""
        if self._handle is None:
            raise LogitechError("设备没有连接")

        request = bytearray(self.packet_length)
        request[0] = self.report_id
        request[1] = self.index
        request[2] = feature_index
        # The low nibble is a software id; responses echo it back. Using a
        # constant id keeps the matching simple and is what the reference
        # implementations do.
        request[3] = ((function & 0x0F) << 4) | 0x01
        for offset, value in enumerate(params):
            if 4 + offset < len(request):
                request[4 + offset] = value & 0xFF

        try:
            self._handle.write(bytes(request))
        except OSError as exc:
            raise LogitechError(f"写入失败：{exc}") from exc

        deadline = time.monotonic() + 0.45
        while time.monotonic() < deadline:
            try:
                answer = self._handle.read(self.packet_length, timeout_ms=60)
            except OSError as exc:
                raise LogitechError(f"读取失败：{exc}") from exc
            if not answer or len(answer) < 4:
                continue
            data = bytes(answer)
            if (data[0] != self.report_id or data[1] != self.index
                    or data[2] != feature_index):
                continue
            if (data[3] >> 4) != (function & 0x0F):
                continue
            # Bit 7 of the function byte marks an error response.
            if data[3] & 0x80:
                return None
            return data
        return None

    def feature_index(self, feature_id: int) -> int | None:
        """Looks up the index of a feature in the device's feature table."""
        answer = self._call(0x00, 0x00, feature_id >> 8, feature_id & 0xFF)
        if not answer:
            return None
        # The feature index is at offset 4 in a HID++ 2.0 response. A few
        # older receivers put it at 5 or 6, so accept the first non-zero
        # value in that short range.
        for offset in (4, 5, 6):
            if len(answer) > offset and answer[offset]:
                return answer[offset]
        return None

    def device_name(self) -> str:
        """Reads the HID++ device name, or returns an empty string."""
        index = self.feature_index(FEATURE_DEVICE_NAME)
        if index is None:
            return ""
        answer = self._call(index, 0x00)
        if not answer or len(answer) < 5:
            return ""
        length = answer[4]
        if not 1 <= length <= 64:
            return ""
        name = bytearray()
        while len(name) < length:
            fragment = self._call(index, 0x10, len(name))
            if not fragment or len(fragment) < 5:
                break
            chunk = fragment[4:4 + (length - len(name))]
            if not chunk:
                break
            name.extend(chunk)
        try:
            return bytes(name).decode("utf-8", errors="replace").strip("\x00")
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Battery
    # ------------------------------------------------------------------

    def battery(self) -> tuple[int, bool] | None:
        """Reads a percentage and the charging flag, or ``None``."""
        index = self.feature_index(FEATURE_BATTERY_STATUS)
        if index is not None:
            answer = self._call(index, 0x00)
            if answer and len(answer) >= 7:
                level = answer[4]
                status = answer[6]
                charging = status in (STATUS_CHARGING,
                                      STATUS_CHARGING_NEARLY_FULL,
                                      STATUS_CHARGING_SLOW)
                if level == 0:
                    if status == STATUS_FULL:
                        level = 100
                    elif charging:
                        # Several devices report 0 while charging. Showing
                        # an empty battery in that state is misleading, so
                        # use a conservative estimate.
                        level = 80
                return max(0, min(100, level)), charging or status == STATUS_FULL

        index = self.feature_index(FEATURE_UNIFIED_BATTERY)
        if index is not None:
            answer = self._call(index, 0x00)
            if answer and len(answer) >= 7:
                level = answer[4]
                coarse = answer[5]
                status = answer[6]
                charging = status in (STATUS_CHARGING,
                                      STATUS_CHARGING_NEARLY_FULL,
                                      STATUS_CHARGING_SLOW,
                                      STATUS_FULL)
                if level == 0:
                    # Some devices only report a coarse bucket.
                    level = {8: 100, 4: 75, 2: 25, 1: 5}.get(coarse, 0)
                return max(0, min(100, level)), charging

        index = self.feature_index(FEATURE_BATTERY_VOLTAGE)
        if index is not None:
            answer = self._call(index, 0x00)
            if answer and len(answer) >= 6:
                millivolts = (answer[4] << 8) | answer[5]
                if 2000 <= millivolts <= 5000:
                    return _voltage_percent(millivolts), False
        return None

    def close(self) -> None:
        """Releases the HID handle."""
        if self._handle is not None:
            try:
                self._handle.close()
            except Exception:
                pass
            self._handle = None


def _interfaces() -> list[dict]:
    """Returns the vendor HID interfaces that can carry HID++."""
    found = []
    for dev in hidsupport.enumerate_interfaces(LOGITECH_VID):
        if dev.get("vendor_id") != LOGITECH_VID:
            continue
        if dev.get("usage_page") != HIDPP_USAGE_PAGE:
            continue
        found.append(dev)
    # Prefer the long-report interface (usually collection 1).
    found.sort(key=lambda d: (d.get("usage", 0), d.get("interface_number", 0)))
    return found


def _indices_for(product_string: str) -> tuple[int, ...]:
    """Returns the device indices to try for one interface."""
    if "receiver" in product_string.lower():
        return RECEIVER_INDICES
    return DIRECT_INDICES + RECEIVER_INDICES


def read_devices() -> list[LogitechDevice]:
    """Reads the battery of every reachable Logitech wireless device."""
    result: list[LogitechDevice] = []
    seen: set[tuple[int, int, str]] = set()

    for dev in _interfaces():
        product_id = dev.get("product_id", 0)
        product_string = dev.get("product_string") or ""
        path = dev["path"]
        if isinstance(path, bytes):
            path = path.decode("utf-8", errors="replace")
        is_receiver = "receiver" in product_string.lower()

        answered: set[int] = set()
        for report_id, length in ((REPORT_LONG, LONG_LENGTH),
                                  (REPORT_SHORT, SHORT_LENGTH)):
            for index in _indices_for(product_string):
                if index in answered:
                    continue
                key = (product_id, index, path.lower())
                if key in seen:
                    continue
                try:
                    controller = LogitechHidpp(
                        path, product_id, product_string, index,
                        report_id, length)
                except LogitechError:
                    continue
                try:
                    try:
                        battery = controller.battery()
                    except LogitechError:
                        continue
                    if battery is None:
                        continue
                    try:
                        name = controller.device_name()
                    except LogitechError:
                        name = ""
                finally:
                    controller.close()
                percent, charging = battery
                if percent <= 0:
                    continue

                if not name:
                    if is_receiver:
                        name = f"Logitech 接收器 #{index}"
                    else:
                        name = product_string or \
                            f"Logitech 设备 {product_id:04X}"

                seen.add(key)
                answered.add(index)
                result.append(LogitechDevice(
                    name=name,
                    percent=percent,
                    charging=charging,
                    kind=_kind_from_name(name),
                    connection=_connection_from_path(path, product_string),
                    product_id=product_id,
                ))
                if not is_receiver:
                    # A directly connected device answers on one index.
                    break
            if answered:
                # The long report worked for at least one device; do not
                # query the same devices again with the short report.
                break

    return result
