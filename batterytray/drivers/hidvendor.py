"""Battery levels for several 2.4 GHz mice with simple HID protocols.

Many smaller mouse brands use one of a handful of reference designs (Nordic
nRF, ATK/VXE, Endgame Gear, VAXEE). Their protocols are short request /
response exchanges over a vendor HID collection. The definitions below are
ported from the public ``2.4G-battery-viewer`` project, which collects and
documents them:

    yszyszysz233/2.4G-battery-viewer - battery.py

Only the battery query is used here; no settings are written.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import hid

# The vendor collections are matched by vendor id and usage page, not by
# product id, because one receiver may serve several model ids.
@dataclass(frozen=True)
class VendorProtocol:
    """One request/response description."""

    name: str
    vendor_id: int
    usage_page: int
    report_id: int
    payload: tuple[int, ...]
    length: int
    level_offset: int
    mode: str = "output"
    wait_ms: int = 120
    scale: int = 1
    level_max: int | None = None
    charging_offset: int | None = None
    voltage_offset: int | None = None
    expect: tuple[tuple[int, int], ...] = ()
    retries: int = 2
    connection: str = "2.4G"


PROTOCOLS: tuple[VendorProtocol, ...] = (
    # ATK / VXE / VGN, newer Nordic 54L15 design.
    VendorProtocol(
        name="ATK / VXE 无线鼠标",
        vendor_id=0x373B, usage_page=0xFF05,
        report_id=0x08, payload=(0x7D, 0x72, 0x02, 0x00, 0x01, 0x07, 0x01),
        length=64, level_offset=7, level_max=100, wait_ms=100,
        expect=((1, 0x72), (5, 0x07)), retries=3,
    ),
    # ATK / VXE / VGN, older Nordic 52840 design.
    VendorProtocol(
        name="ATK / VXE 无线鼠标",
        vendor_id=0x373B, usage_page=0xFF02,
        report_id=0x08,
        payload=(0x04,) + (0x00,) * 15 + (0x49,),
        length=17, level_offset=6, level_max=100, wait_ms=100,
        retries=3,
    ),
    VendorProtocol(
        name="VXE / VGN 无线鼠标",
        vendor_id=0x3554, usage_page=0xFF02,
        report_id=0x08,
        payload=(0x04,) + (0x00,) * 15 + (0x49,),
        length=17, level_offset=6, level_max=100, wait_ms=100,
        retries=3,
    ),
    # Endgame Gear XM2w / OP1W.
    VendorProtocol(
        name="Endgame Gear 无线鼠标",
        vendor_id=0x3367, usage_page=0xFF01,
        report_id=0xA1, payload=(0xB4,), length=64, level_offset=16,
        mode="feature", wait_ms=350, voltage_offset=17,
        expect=((1, 0x01),), retries=3,
    ),
    # VAXEE / ZYGEN, including the 4K receiver.
    VendorProtocol(
        name="VAXEE / ZYGEN 无线鼠标",
        vendor_id=0x3057, usage_page=0xFF05,
        report_id=0x0E, payload=(0xA5, 0x0B, 0x01, 0x01), length=64,
        level_offset=5, mode="feature", wait_ms=120, scale=5, level_max=20,
    ),
    # Generic Nordic nRF 2.4 GHz receiver.
    VendorProtocol(
        name="Nordic nRF 无线设备",
        vendor_id=0x1915, usage_page=0xFFA0,
        report_id=0x05, payload=(0x15, 0x00, 0x00, 0x01), length=32,
        level_offset=9, mode="feature", wait_ms=90,
    ),
)

_KEYBOARD_WORDS = ("keyboard", "keys", "k380", "k400", "k650", "k780",
                   "k800", "k830", "k850", "mx keys", "keychron", "qmk")

# VXE / ATK keyboards use a different vendor collection than the mice. A
# 64-byte report 0x04 asks for status block 0x1A; the reply carries the
# percentage at byte 8 and the charging flag at byte 9.
VXE_KEYBOARD_VID = 0x320F
VXE_KEYBOARD_PIDS = (0x5088,)
VXE_KEYBOARD_USAGE_PAGE = 0xFF1C
VXE_REQUEST_REPORT = 0x04
VXE_STATUS_BLOCK = 0x1A

# The request and the reply are short; the keyboard answers in well under a
# second when awake. The result is cached so a normal poll does not repeat it.
_VXE_READ_TIMEOUT = 2.0
_VXE_CACHE: dict[str, tuple[float, HidBatteryDevice | None]] = {}
_VXE_OK_TTL = 50.0
_VXE_FAIL_TTL = 15.0


def _vxe_request() -> bytes:
    """Builds the 64-byte status request for a VGN/VXE keyboard."""
    request = bytearray(64)
    request[0] = VXE_REQUEST_REPORT
    request[3] = VXE_STATUS_BLOCK
    request[4] = 0x06
    return bytes(request)


def _vxe_percent(data: bytes) -> tuple[int, bool] | None:
    """Returns (percentage, charging) from a VGN keyboard status reply."""
    if (len(data) < 10 or data[0] != VXE_REQUEST_REPORT
            or data[3] != VXE_STATUS_BLOCK):
        return None
    percent = data[8]
    if not 1 <= percent <= 100:
        return None
    return percent, data[9] != 0


class HidVendorError(Exception):
    """The device did not answer the battery query."""


@dataclass(frozen=True)
class HidBatteryDevice:
    """One device that answered a vendor battery query."""

    name: str
    percent: int
    charging: bool
    kind: str
    connection: str
    product_id: int
    connected: bool = True


def _kind_from_name(name: str) -> str:
    """Guesses the device kind from its product name."""
    lowered = name.lower()
    return "keyboard" if any(word in lowered for word in _KEYBOARD_WORDS) \
        else "mouse"


def _path_text(path: bytes | str) -> str:
    if isinstance(path, bytes):
        return path.decode("utf-8", errors="replace")
    return path


def _read_until(handle, length: int, protocol: VendorProtocol,
                timeout_ms: int = 700) -> bytes:
    """Reads input reports until one matches the protocol's signature."""
    deadline = time.monotonic() + timeout_ms / 1000.0
    last = b""
    while time.monotonic() < deadline:
        try:
            report = handle.read(length, timeout_ms=80)
        except OSError as exc:
            raise HidVendorError(f"读取失败：{exc}") from exc
        if not report:
            continue
        data = bytes(report)
        last = data
        if not protocol.expect:
            return data
        if all(len(data) > offset and data[offset] == value
               for offset, value in protocol.expect):
            return data
    return last


def _query(handle, protocol: VendorProtocol) -> bytes:
    """Sends one request and returns the response."""
    body = bytes([protocol.report_id] + list(protocol.payload))
    body = (body + bytes(protocol.length))[:protocol.length]

    for _ in range(max(1, protocol.retries)):
        # Drop stale input reports before the request. Without this a
        # button event can be mistaken for the answer.
        for _ in range(8):
            try:
                if not handle.read(protocol.length, timeout_ms=1):
                    break
            except OSError:
                break

        try:
            if protocol.mode == "feature":
                handle.send_feature_report(body)
                time.sleep(protocol.wait_ms / 1000.0)
                answer = bytes(handle.get_feature_report(protocol.report_id,
                                                        protocol.length))
                if protocol.expect and not all(
                        len(answer) > offset and answer[offset] == value
                        for offset, value in protocol.expect):
                    continue
                return answer
            handle.write(body)
        except OSError as exc:
            raise HidVendorError(f"写入失败：{exc}") from exc

        time.sleep(protocol.wait_ms / 1000.0)
        answer = _read_until(handle, protocol.length, protocol)
        if answer:
            return answer
    raise HidVendorError("设备没有响应")


def _parse(protocol: VendorProtocol, answer: bytes) -> tuple[int, bool]:
    """Turns a response into a percentage and a charging flag."""
    if len(answer) <= protocol.level_offset:
        raise HidVendorError("回复长度不足")
    raw = answer[protocol.level_offset]
    if protocol.level_max is not None and raw > protocol.level_max:
        raise HidVendorError(f"电量字节 0x{raw:02X} 超出范围")
    percent = max(0, min(100, raw * protocol.scale))
    charging = False
    if protocol.charging_offset is not None:
        if len(answer) > protocol.charging_offset:
            charging = answer[protocol.charging_offset] != 0
    # Some protocols report voltage; it is not needed when the device
    # already gave a percentage, so it is intentionally ignored.
    return percent, charging


def _candidate_interfaces() -> list[tuple[dict, VendorProtocol]]:
    """Returns one (HID interface, protocol) pair for every match."""
    result = []
    seen: set[tuple[int, int, str]] = set()
    for dev in hid.enumerate():
        vid = dev.get("vendor_id")
        page = dev.get("usage_page")
        if not isinstance(page, int):
            continue
        for protocol in PROTOCOLS:
            if vid != protocol.vendor_id or page != protocol.usage_page:
                continue
            path = _path_text(dev.get("path", ""))
            key = (vid, protocol.report_id, path.lower())
            if key in seen:
                continue
            seen.add(key)
            result.append((dev, protocol))
    return result


def read_vxe_keyboards() -> list[HidBatteryDevice]:
    """Reads VXE/ATK keyboards through their status block.

    The keyboard answers report ``04 .. .. 1A 06`` with a status block:
    ``04 00 00 1A 06 00 00 00 <percent> <charging> ...``. It sleeps when
    unused, so a failed read is cached briefly and retried on a later poll.
    """
    found: list[HidBatteryDevice] = []
    for dev in hid.enumerate(VXE_KEYBOARD_VID):
        if dev.get("product_id") not in VXE_KEYBOARD_PIDS:
            continue
        if dev.get("usage_page") != VXE_KEYBOARD_USAGE_PAGE:
            continue
        raw_path = dev.get("path", b"")
        path = _path_text(raw_path)
        cache_key = path.lower()
        cached = _VXE_CACHE.get(cache_key)
        if cached is not None:
            age = time.monotonic() - cached[0]
            if cached[1] is not None and age < _VXE_OK_TTL:
                found.append(cached[1])
                continue
            if cached[1] is None and age < _VXE_FAIL_TTL:
                continue

        try:
            handle = hid.device()
            handle.open_path(raw_path)
        except OSError:
            continue

        reading = None
        try:
            # Drop reports left over from an earlier command, then ask.
            for _ in range(8):
                if not handle.read(64, timeout_ms=1):
                    break
            handle.write(_vxe_request())
            deadline = time.monotonic() + _VXE_READ_TIMEOUT
            while time.monotonic() < deadline:
                try:
                    answer = handle.read(64, timeout_ms=150)
                except OSError:
                    break
                if not answer:
                    continue
                parsed = _vxe_percent(bytes(answer))
                if parsed is None:
                    continue
                percent, charging = parsed
                name = (dev.get("product_string") or "VXE 键盘")
                for suffix in (" 2.4G Dongle", " Dongle", " 2.4G"):
                    if name.endswith(suffix):
                        name = name[:-len(suffix)]
                        break
                reading = HidBatteryDevice(
                    name=name,
                    percent=percent,
                    charging=charging,
                    kind="keyboard",
                    connection="2.4G",
                    product_id=dev.get("product_id", 0),
                )
                break
        except OSError:
            pass
        finally:
            try:
                handle.close()
            except Exception:
                pass

        _VXE_CACHE[cache_key] = (time.monotonic(), reading)
        if reading is not None:
            found.append(reading)
    return found


def read_devices() -> list[HidBatteryDevice]:
    """Reads every device that answers one of the documented protocols."""
    found: list[HidBatteryDevice] = []
    seen_names: set[str] = set()

    for dev, protocol in _candidate_interfaces():
        path = _path_text(dev.get("path", ""))
        try:
            handle = hid.device()
            handle.open_path(path)
        except OSError:
            continue

        try:
            answer = _query(handle, protocol)
            percent, charging = _parse(protocol, answer)
        except HidVendorError:
            continue
        finally:
            try:
                handle.close()
            except Exception:
                pass

        if percent <= 0:
            continue
        name = dev.get("product_string") or protocol.name
        # A receiver often reports the same product string for every
        # paired device. Fall back to the protocol name in that case.
        if name.lower() in ("usb receiver", "2.4g receiver", "receiver"):
            name = protocol.name
        key = name.lower()
        if key in seen_names:
            continue
        seen_names.add(key)

        found.append(HidBatteryDevice(
            name=name,
            percent=percent,
            charging=charging,
            kind=_kind_from_name(name),
            connection=protocol.connection,
            product_id=dev.get("product_id", 0),
        ))

    for keyboard in read_vxe_keyboards():
        key = keyboard.name.lower()
        if key in seen_names:
            continue
        seen_names.add(key)
        found.append(keyboard)

    return found
