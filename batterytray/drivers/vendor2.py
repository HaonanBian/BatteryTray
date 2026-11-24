"""Battery levels for the vendor HID protocols of more mice and keyboards.

The protocols in this module were ported from the open-source projects listed
at the bottom. They all follow the same shape: a short request is written to
a vendor HID collection and the answer is read back from the same collection.

Every protocol here is read-only. Only the battery level is read; no setting
is written and nothing is stored on the device.

The frame layouts are documented next to the code that builds them, so a
protocol can be checked against its source without digging through this file.

References:
    435311382/Volt                       - the frame layouts and the model table
    fisher44123/volt-battery-monitor     - the Compx and the 狼蛛 layouts
    mammadow/keychron-battery-tray       - the Keychron vendor collection
    incconutwo/mouse-battery-tray        - the WLMouse and the Pulsar layouts
    ryanlewis/mousebatt                  - the Pulsar XS-1 frames
    ahutsunboy/2.4g-battery-tray-python  - the 迈从 and the 狼蛛 receivers
    LORQAQ/mchose-tray                  - the MCHOSE control collection
    VoltWalt/scyrox-v6-kde-battery       - the Compx frame and its checksum
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import hid

from . import hidsupport

from . import devices


@dataclass(frozen=True)
class VendorDevice:
    """One device that answered a vendor battery query."""

    name: str
    percent: int
    charging: bool
    kind: str
    connection: str
    product_id: int
    vendor_id: int = 0
    protocol: str = ""


class VendorError(Exception):
    """The device did not answer the battery query."""


# ----------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------

def _path_text(path: bytes | str) -> str:
    """The HID path as text."""
    if isinstance(path, bytes):
        return path.decode("utf-8", errors="replace")
    return path


def _drain(handle, length: int, rounds: int = 8) -> None:
    """Throws away the input reports that are still queued.

    Without this an old answer — or a button event — can be mistaken for the
    answer to the request that was just sent.
    """
    for _ in range(rounds):
        try:
            if not handle.read(length, timeout_ms=1):
                break
        except OSError:
            break


def _read_until(handle, length: int, accept, timeout_ms: int = 700) -> bytes | None:
    """Reads input reports until one is accepted.

    ``accept`` receives the report as bytes and returns whether it is the
    answer that was asked for.
    """
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        try:
            report = handle.read(length, timeout_ms=80)
        except OSError:
            return None
        if not report:
            continue
        data = bytes(report)
        if accept(data):
            return data
    return None


def _write(handle, data: bytes) -> None:
    """Writes an output report."""
    try:
        handle.write(data)
    except OSError as exc:
        raise VendorError(f"写入失败：{exc}") from exc


def _feature(handle, data: bytes, report_id: int, length: int) -> bytes | None:
    """Sends a feature report and reads the answer back.

    The answer of a feature report is the same buffer the device keeps, so it
    is read with the same report id.
    """
    try:
        handle.send_feature_report(data)
    except OSError as exc:
        raise VendorError(f"写入失败：{exc}") from exc

    time.sleep(0.08)
    try:
        return bytes(handle.get_feature_report(report_id, length))
    except OSError:
        return None


# ----------------------------------------------------------------------
# The Compx 17 byte family — ATK, VXE, VGN, Pulsar, Scyrox, 达尔优 and
# the other brands that share the same reference design.
#
# The frame is ``08 <command> <body> <checksum>`` and the sum of all 17
# bytes has to be ``0x55``. The shortest request that reads the level is
# ``08 04`` with a checksum of ``0x49``.
#
# The answer is ``08 04 00 00 00 <status> <level> <charging> <mv> <mv>``.
# ----------------------------------------------------------------------

COMPX_USAGE_PAGE = 0xFF02


def _compx_frame(command: int, body: bytes = b"") -> bytes:
    """Builds a 17 byte Compx frame."""
    frame = bytearray(17)
    frame[0] = 0x08
    frame[1] = command
    if body:
        frame[2:2 + len(body)] = body[:15]
    frame[16] = (0x55 - sum(frame[:16])) & 0xFF
    return bytes(frame)


def _is_compx_reply(data: bytes, command: int = 0x04) -> bool:
    """Whether a frame is the answer to a Compx request.

    The report id and the command alone are not enough: the same collection
    also carries other traffic, and taking its level byte as the battery
    level produces values like 116 or 123. The checksum check drops those.
    """
    if len(data) < 17:
        return False
    if data[0] != 0x08 or data[1] != command:
        return False
    return (sum(data[:17]) & 0xFF) == 0x55


def _parse_compx(data: bytes) -> tuple[int, bool] | None:
    """Reads the level out of a Compx answer."""
    if not _is_compx_reply(data):
        return None
    percent = data[6]
    if not 0 <= percent <= 100:
        return None
    return percent, data[7] != 0


def _read_compx(handle) -> tuple[int, bool] | None:
    """Reads the battery level over the Compx frame."""
    _drain(handle, 17)
    _write(handle, _compx_frame(0x04))

    time.sleep(0.12)
    answer = _read_until(handle, 17, lambda data: _parse_compx(data) is not None)
    if answer is None:
        return None
    return _parse_compx(answer)


# ----------------------------------------------------------------------
# The Pulsar XS-1 — a 64 byte feature frame with a two byte checksum.
#
# The request is a feature buffer whose first byte is the report id 0x00,
# followed by the three command bytes and the payload. The answer repeats
# the command and carries the level at frame byte 6.
# ----------------------------------------------------------------------

PULSAR_XS1_USAGE_PAGE = 0xFFFF
PULSAR_XS1_USAGE = 0x0001
PULSAR_XS1_FRAME = 64

# The report id of the feature buffer.
PULSAR_XS1_REPORT_ID = 0x00

# The commands of the XS-1 protocol.
PULSAR_XS1_CMD_BATTERY = (0x08, 0x81, 0x01)
PULSAR_XS1_CMD_CHARGING = (0x08, 0x83, 0x01)

# The status byte of a real answer.
PULSAR_XS1_STATUS_ANSWER = 0x01


def _xs1_checksum(frame: bytes) -> bytes:
    """The two byte checksum of an XS-1 frame."""
    total = sum(frame[:PULSAR_XS1_FRAME - 2]) & 0xFFFF
    return total.to_bytes(2, "little")


def _xs1_request(command: tuple[int, int, int]) -> bytes:
    """Builds an XS-1 feature request.

    The feature buffer starts with the report id, and the frame behind it
    holds the status byte, the command, the payload and the checksum.
    """
    frame = bytearray(PULSAR_XS1_FRAME)
    frame[1:4] = bytes(command)
    frame[PULSAR_XS1_FRAME - 2:] = _xs1_checksum(bytes(frame))
    return bytes([PULSAR_XS1_REPORT_ID]) + bytes(frame)


def _xs1_payload(answer: bytes, command: tuple[int, int, int]) -> bytes | None:
    """The frame of an answer to ``command``, or ``None``."""
    if len(answer) < 1 + PULSAR_XS1_FRAME:
        return None
    frame = answer[1:1 + PULSAR_XS1_FRAME]
    if frame[0] != PULSAR_XS1_STATUS_ANSWER:
        return None
    if tuple(frame[1:3]) != command[:2]:
        return None
    if frame[PULSAR_XS1_FRAME - 2:] != _xs1_checksum(bytes(frame)):
        return None
    return bytes(frame)


def _read_pulsar_xs1(handle) -> tuple[int, bool] | None:
    """Reads the battery level over the Pulsar XS-1 protocol."""
    battery = _feature(handle, _xs1_request(PULSAR_XS1_CMD_BATTERY),
                       0, 1 + PULSAR_XS1_FRAME)
    if battery is None:
        return None
    frame = _xs1_payload(battery, PULSAR_XS1_CMD_BATTERY)
    if frame is None or frame[6] > 100:
        return None
    percent = frame[6]

    charging = False
    state = _feature(handle, _xs1_request(PULSAR_XS1_CMD_CHARGING),
                     0, 1 + PULSAR_XS1_FRAME)
    if state is not None:
        state_frame = _xs1_payload(state, PULSAR_XS1_CMD_CHARGING)
        if state_frame is not None:
            charging = state_frame[6] != 0
    return percent, charging


# ----------------------------------------------------------------------
# The AULA 20 byte family — AULA, LEOBOG, 狼蛛 and 凌豹.
#
# The receiver answers with two different shapes and both have to be known,
# otherwise one of them looks like silence:
#     ``13 4A 01 00 02 <level> <status>``
#     ``13 0A 01 00 04 05 <level> <status>``
# The status byte is 0x10 while charging and 0x01 while discharging.
# ----------------------------------------------------------------------

AULA_USAGE_PAGE = 0xFF02


def _aula_frame(command: bytes, length: int = 20) -> bytes:
    """Builds an AULA frame.

    The last byte is the low byte of the sum of the bytes before it.
    """
    frame = bytearray(length)
    frame[0] = 0x13
    frame[1:1 + len(command)] = command
    frame[length - 1] = sum(frame[:length - 1]) & 0xFF
    return bytes(frame)


def _parse_aula(data: bytes) -> tuple[int, bool] | None:
    """Reads the level out of an AULA answer."""
    if len(data) < 8 or data[0] != 0x13:
        return None
    if data[1] == 0x4A and data[2] == 0x01 and data[4] == 0x02:
        level_offset, status_offset = 5, 6
    elif data[1] == 0x0A and data[2] == 0x01 and data[4] == 0x04:
        level_offset, status_offset = 6, 7
    else:
        return None
    percent = data[level_offset]
    if not 0 <= percent <= 100:
        return None
    return percent, data[status_offset] == 0x10


def _read_aula(handle) -> tuple[int, bool] | None:
    """Reads the battery level over the AULA frame.

    The receivers answer two different queries. The first one is the short
    ``13 CA`` command, the second one is the ``13 05 01`` command the
    keyboard makers use. Both are tried.
    """
    for command, length in ((bytes([0xCA]), 20),
                             (bytes([0x05, 0x01, 0x00, 0x0A, 0x03]), 20),
                             (bytes([0x05, 0x01, 0x00, 0x0A, 0x03]), 64)):
        _drain(handle, length)
        try:
            handle.write(_aula_frame(command, length))
        except OSError as exc:
            raise VendorError(f"写入失败：{exc}") from exc

        time.sleep(0.25)
        answer = _read_until(handle, length,
                             lambda data: _parse_aula(data) is not None,
                             timeout_ms=800)
        if answer is None:
            continue
        parsed = _parse_aula(answer)
        if parsed is not None:
            return parsed
    return None

# ----------------------------------------------------------------------
# Keychron — the vendor collection with usage page 0xFFC1.
#
# The request is a 64 byte output report whose first two bytes are the
# report id 0xB3 and the command 0x06. The answer repeats them as 0xB4 and
# carries the level in byte 20: the lower seven bits are the percentage and
# the top bit is the charging flag.
# ----------------------------------------------------------------------

KEYCHRON_USAGE_PAGE = 0xFFC1

KEYCHRON_REPORT_CMD = 0xB3
KEYCHRON_REPORT_RESP = 0xB4
KEYCHRON_CMD_STATUS = 0x06

KEYCHRON_BATTERY_OFFSET = 20
KEYCHRON_BATTERY_CHARGING = 0x80
KEYCHRON_BATTERY_LEVEL = 0x7F


def _keychron_request() -> bytes:
    """Builds the Keychron status request."""
    frame = bytearray(64)
    frame[0] = KEYCHRON_REPORT_CMD
    frame[1] = KEYCHRON_CMD_STATUS
    return bytes(frame)


def _parse_keychron(data: bytes) -> tuple[int, bool] | None:
    """Reads the level out of a Keychron answer."""
    if len(data) <= KEYCHRON_BATTERY_OFFSET:
        return None
    if data[0] != KEYCHRON_REPORT_RESP or data[1] != KEYCHRON_CMD_STATUS:
        return None
    raw = data[KEYCHRON_BATTERY_OFFSET]
    percent = raw & KEYCHRON_BATTERY_LEVEL
    if percent > 100:
        return None
    return percent, (raw & KEYCHRON_BATTERY_CHARGING) != 0


def _read_keychron(handle) -> tuple[int, bool] | None:
    """Reads the battery level over the Keychron protocol."""
    _drain(handle, 64)
    _write(handle, _keychron_request())

    time.sleep(0.1)
    answer = _read_until(handle, 64, lambda data: _parse_keychron(data) is not None)
    if answer is None:
        return None
    return _parse_keychron(answer)


# ----------------------------------------------------------------------
# Rapoo / 雷柏 — the dongle pushes a status packet, nothing is sent.
#
# The layout is:
#     ``[0]``    the report id, ``0x07``
#     ``[1]``    the device id, ``0x20`` behind a receiver
#     ``[2]``    the DPI stage, counted from zero
#     ``[3..4]`` the X dpi, little endian
#     ``[5..6]`` the Y dpi, little endian
#     ``[7]``    the active flag, ``0x01`` while the mouse is awake
#     ``[8]``    the battery level
# ----------------------------------------------------------------------

RAPOO_USAGE_PAGE = 0xFF00
RAPOO_REPORT_ID = 0x07


def _parse_rapoo(data: bytes) -> tuple[int, bool] | None:
    """Reads the level out of a Rapoo status packet."""
    if len(data) < 9:
        return None
    if data[0] != RAPOO_REPORT_ID:
        # A few interfaces prepend an alignment byte.
        if len(data) > 9 and data[1] == RAPOO_REPORT_ID:
            data = data[1:]
        else:
            return None
    percent = data[8]
    if not 0 <= percent <= 100:
        return None
    return percent, False


def _read_rapoo(handle, length: int = 19) -> tuple[int, bool] | None:
    """Reads the level out of the packets the Rapoo dongle pushes."""
    answer = _read_until(handle, length,
                         lambda data: _parse_rapoo(data) is not None,
                         timeout_ms=1500)
    if answer is None:
        return None
    return _parse_rapoo(answer)


# ----------------------------------------------------------------------
# MCHOSE — the control collection with the inverted payload.
#
# The payload of a control report is 20 bytes and every byte of it is sent
# inverted. The answer echoes the command in its second byte, again
# inverted, and carries the device information behind it:
#     ``[0..1]`` the device vid
#     ``[2..3]`` the device pid
#     ``[4..7]`` the firmware version
#     ``[8]``    the connection mode
#     ``[9]``    the battery level
#     ``[10]``   the charging flag
#
# The chip sometimes answers with the buffer of the previous command, so an
# answer whose payload is all zeros is rejected as well.
# ----------------------------------------------------------------------

MCHOSE_USAGE_PAGE = 0xFF01
MCHOSE_USAGE = 0x0001

MCHOSE_REPORT_CONTROL = 0x11
MCHOSE_CMD_DEVICE_INFO = 0x06
MCHOSE_PAYLOAD = 20


def _mchose_request(command: int) -> bytes:
    """Builds a MCHOSE control request."""
    frame = bytearray(1 + MCHOSE_PAYLOAD)
    frame[0] = MCHOSE_REPORT_CONTROL
    for i in range(MCHOSE_PAYLOAD):
        frame[1 + i] = 0xFF
    frame[1] = command ^ 0xFF
    return bytes(frame)


def _parse_mchose(answer: bytes, command: int) -> bytes | None:
    """Decodes a MCHOSE answer."""
    if len(answer) < 1 + MCHOSE_PAYLOAD:
        return None
    if answer[1] != (command ^ 0xFF):
        return None
    payload = bytes(b ^ 0xFF for b in answer[2:1 + MCHOSE_PAYLOAD])
    if not any(payload):
        return None
    return payload


def _read_mchose(handle) -> tuple[int, bool] | None:
    """Reads the battery level over the MCHOSE protocol."""
    for _ in range(4):
        answer = _feature(handle, _mchose_request(MCHOSE_CMD_DEVICE_INFO),
                          MCHOSE_REPORT_CONTROL, 1 + MCHOSE_PAYLOAD)
        if answer is None:
            continue
        payload = _parse_mchose(answer, MCHOSE_CMD_DEVICE_INFO)
        if payload is None or len(payload) < 11:
            continue
        percent = payload[9]
        charging = payload[10] != 0
        if percent > 100:
            continue
        # A level of zero without charging means the mouse did not answer.
        if percent == 0 and not charging:
            continue
        return percent, charging
    return None


# ----------------------------------------------------------------------
# Lamzu — a feature report with the level at byte 8.
# ----------------------------------------------------------------------

LAMZU_USAGE_PAGE = 0xFF00


def _lamzu_request() -> bytes:
    """Builds the Lamzu request."""
    frame = bytearray(65)
    frame[3] = 0x02
    frame[4] = 0x02
    frame[6] = 0x83
    return bytes(frame)


def _parse_lamzu(data: bytes) -> tuple[int, bool] | None:
    """Reads the level out of a Lamzu answer."""
    if len(data) < 9:
        return None
    if data[1] != 0xA1 or data[6] != 0x83:
        return None
    percent = data[8]
    if not 1 <= percent <= 100:
        return None
    return percent, data[7] == 0x01


def _read_lamzu(handle) -> tuple[int, bool] | None:
    """Reads the battery level over the Lamzu protocol."""
    for _ in range(3):
        answer = _feature(handle, _lamzu_request(), 0, 65)
        if answer is None:
            continue
        parsed = _parse_lamzu(answer)
        if parsed is not None:
            return parsed
    return None


# ----------------------------------------------------------------------
# Ninjutso — the Nordic nRF feature report.
#
# The answer carries the level at byte 9, the charging flag at byte 10, the
# full flag at byte 11 and the online flag at byte 12.
# ----------------------------------------------------------------------

NINJUTSO_USAGE_PAGE = 0xFF00


def _ninjutso_request() -> bytes:
    """Builds the Ninjutso request."""
    frame = bytearray(32)
    frame[0] = 0x05
    frame[1] = 0x15
    frame[4] = 0x01
    return bytes(frame)


def _parse_ninjutso(data: bytes) -> tuple[int, bool] | None:
    """Reads the level out of a Ninjutso answer."""
    if len(data) < 13:
        return None
    percent = data[9]
    if not 1 <= percent <= 100:
        return None
    if data[11]:
        return percent, True
    return percent, data[10] != 0


def _read_ninjutso(handle) -> tuple[int, bool] | None:
    """Reads the battery level over the Ninjutso protocol."""
    for _ in range(3):
        answer = _feature(handle, _ninjutso_request(), 0, 32)
        if answer is None:
            continue
        parsed = _parse_ninjutso(answer)
        if parsed is not None:
            return parsed
    return None


# ----------------------------------------------------------------------
# HyperX — the 20 byte Cloud Flight frame.
#
# The answer starts with ``21 FF 05``, then the state byte and the level.
# The level is a bucket from 1 to 10, so it has to be multiplied by ten.
# ----------------------------------------------------------------------

HYPERX_USAGE_PAGE = 0xFF00


def _hyperx_request(length: int = 20) -> bytes:
    """Builds the HyperX request."""
    frame = bytearray(length)
    frame[0] = 0x21
    frame[1] = 0xFF
    frame[2] = 0x05
    return bytes(frame)


def _parse_hyperx(data: bytes) -> tuple[int, bool] | None:
    """Reads the level out of a HyperX answer."""
    if len(data) < 5:
        return None
    if data[0] != 0x21 or data[1] != 0xFF or data[2] != 0x05:
        return None
    state = data[3]
    gauge = data[4] if data[4] else state
    if not 1 <= gauge <= 100:
        return None
    percent = gauge * 10 if gauge <= 10 else gauge
    return percent, state == 0x10


def _read_hyperx(handle) -> tuple[int, bool] | None:
    """Reads the battery level over the HyperX protocol."""
    _drain(handle, 32)
    _write(handle, _hyperx_request())

    time.sleep(0.2)
    answer = _read_until(handle, 32, lambda data: _parse_hyperx(data) is not None)
    if answer is None:
        return None
    return _parse_hyperx(answer)


# ----------------------------------------------------------------------
# A4Tech Bloody — a feature command, then a pushed input report.
#
# The status report is ``06 56 <level> <wired>``. A level of 255 means the
# radio link is down, so the report does not count.
# ----------------------------------------------------------------------

BLOODY_USAGE_PAGE = 0xFF01


def _bloody_command() -> bytes:
    """Builds the Bloody command that asks for the status report."""
    return bytes([0x80, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x80])


def _parse_bloody(data: bytes) -> tuple[int, bool] | None:
    """Reads the level out of a Bloody status report."""
    if len(data) < 4:
        return None
    if data[0] != 0x06 or data[1] != 0x56:
        return None
    if data[2] == 0xFF:
        return None
    percent = data[2]
    if not 1 <= percent <= 100:
        return None
    return percent, data[3] != 0


def _read_bloody(handle) -> tuple[int, bool] | None:
    """Reads the battery level over the Bloody protocol."""
    try:
        handle.send_feature_report(_bloody_command())
    except OSError as exc:
        raise VendorError(f"写入失败：{exc}") from exc

    time.sleep(0.1)
    answer = _read_until(handle, 8, lambda data: _parse_bloody(data) is not None)
    if answer is None:
        return None
    return _parse_bloody(answer)


# ----------------------------------------------------------------------
# Attack Shark — the dongle pushes the level on its own.
#
# The level is at byte 4 and counts in steps of ten percent.
# ----------------------------------------------------------------------

ATTACK_SHARK_USAGE_PAGE = 0x000A


def _parse_attack_shark(data: bytes) -> tuple[int, bool] | None:
    """Reads the level out of an Attack Shark report."""
    if len(data) < 5:
        return None
    if not 1 <= data[4] <= 10:
        return None
    return data[4] * 10, False


def _read_attack_shark(handle, length: int = 8) -> tuple[int, bool] | None:
    """Reads the level out of the reports the dongle pushes."""
    answer = _read_until(handle, length,
                         lambda data: _parse_attack_shark(data) is not None,
                         timeout_ms=1500)
    if answer is None:
        return None
    return _parse_attack_shark(answer)


# ----------------------------------------------------------------------
# SteelSeries — the legacy and the Nova frame families.
#
# The legacy family sends a short command and gets a short answer back. The
# command and the position of the level differ per model, so every model
# has its own entry.
# ----------------------------------------------------------------------

STEELSERIES_USAGE_PAGE = 0xFF00


class _SteelSeriesSpec:
    """The command and the answer layout of one SteelSeries model."""

    __slots__ = ("command", "response_size", "level_byte", "status_byte",
                 "offline_value", "charging_value", "minimum", "maximum")

    def __init__(self, command: tuple[int, int], response_size: int,
                 level_byte: int, status_byte: int, offline_value: int,
                 charging_value: int, minimum: int = 0, maximum: int = 100):
        self.command = command
        self.response_size = response_size
        self.level_byte = level_byte
        self.status_byte = status_byte
        self.offline_value = offline_value
        self.charging_value = charging_value
        self.minimum = minimum
        self.maximum = maximum


# The legacy models: the command bytes, the length of the answer, the
# position of the level and of the status byte.
STEELSERIES_LEGACY: dict[int, _SteelSeriesSpec] = {
    0x12B3: _SteelSeriesSpec((0x06, 0x12), 8, 3, 2, 0x01, 0xFF),
    0x12B6: _SteelSeriesSpec((0x06, 0x12), 8, 3, 2, 0x01, 0xFF),
    0x12D7: _SteelSeriesSpec((0x06, 0x12), 8, 3, 2, 0x01, 0xFF),
    0x12D5: _SteelSeriesSpec((0x06, 0x12), 8, 3, 2, 0x01, 0xFF),
    0x1260: _SteelSeriesSpec((0x06, 0x18), 8, 2, -1, -1, -1),
    0x12AD: _SteelSeriesSpec((0x06, 0x18), 8, 2, -1, -1, -1),
    0x1252: _SteelSeriesSpec((0x06, 0x18), 8, 2, -1, -1, -1),
    0x1280: _SteelSeriesSpec((0x06, 0x18), 8, 2, -1, -1, -1),
    0x12C2: _SteelSeriesSpec((0x00, 0x20), 12, 3, 4, 0xFF, 0x01),
    0x12C4: _SteelSeriesSpec((0x00, 0x20), 12, 3, 4, 0xFF, 0x01),
    0x1290: _SteelSeriesSpec((0x40, 0xAA), 8, 1, -1, -1, -1),
}

# The Nova models: the level is at byte 2 and the status at byte 3. The
# status is 0 while the device is off, 1 or 2 while it is charging.
STEELSERIES_NOVA: dict[int, bool] = {
    0x220E: False, 0x2212: False, 0x2216: False, 0x2236: False,
    0x12EC: False, 0x2269: False, 0x226D: False,
    0x2232: False, 0x2253: False,
    0x2202: True, 0x2206: True, 0x223A: True, 0x227A: True, 0x22A4: True,
    0x220A: False, 0x2298: False, 0x22A7: False,
    0x12E0: False, 0x12E5: False,
    0x230A: False,
}


def _parse_steelseries_legacy(data: bytes,
                               spec: _SteelSeriesSpec) -> tuple[int, bool] | None:
    """Reads the level out of a legacy SteelSeries answer."""
    # The report id is only part of the answer when the answer is longer
    # than the documented one.
    offset = 1 if len(data) > spec.response_size else 0
    if len(data) <= offset + spec.level_byte:
        return None
    if spec.status_byte >= 0 and len(data) > offset + spec.status_byte:
        if data[offset + spec.status_byte] == spec.offline_value:
            return None
    raw = data[offset + spec.level_byte]
    percent = raw
    if spec.maximum > spec.minimum and spec.maximum != 100:
        percent = (raw - spec.minimum) * 100 // (spec.maximum - spec.minimum)
    percent = max(0, min(100, percent))
    charging = False
    if spec.status_byte >= 0 and len(data) > offset + spec.status_byte:
        charging = data[offset + spec.status_byte] == spec.charging_value
    return percent, charging


def _read_steelseries_legacy(handle,
                              spec: _SteelSeriesSpec) -> tuple[int, bool] | None:
    """Reads the battery level over the legacy SteelSeries protocol."""
    frame = bytearray(31)
    frame[0] = spec.command[0]
    frame[1] = spec.command[1]
    _drain(handle, 31)
    _write(handle, bytes(frame))

    time.sleep(0.15)
    answer = _read_until(
        handle, 31,
        lambda data: _parse_steelseries_legacy(data, spec) is not None,
        timeout_ms=700)
    if answer is None:
        return None
    return _parse_steelseries_legacy(answer, spec)


def _parse_steelseries_nova(data: bytes,
                             discrete: bool) -> tuple[int, bool] | None:
    """Reads the level out of a Nova answer."""
    # The answer either starts with the status byte or with the report id.
    offset = 0 if data[0] == 0x20 else 1
    if len(data) <= offset + 3:
        return None
    raw = data[offset + 2]
    status = data[offset + 3]
    if status == 0x00:
        # The device is switched off.
        return None
    percent = raw * 100 // 4 if discrete else raw
    percent = max(0, min(100, percent))
    return percent, status in (0x01, 0x02)


def _read_steelseries_nova(handle,
                            discrete: bool) -> tuple[int, bool] | None:
    """Reads the battery level over the SteelSeries Nova protocol."""
    frame = bytearray(64)
    frame[0] = 0x00
    frame[1] = 0x20
    _drain(handle, 64)
    _write(handle, bytes(frame))

    time.sleep(0.15)
    answer = _read_until(
        handle, 64,
        lambda data: _parse_steelseries_nova(data, discrete) is not None,
        timeout_ms=800)
    if answer is None:
        return None
    return _parse_steelseries_nova(answer, discrete)


# ----------------------------------------------------------------------
# Lofree — the Hyzen keyboard on its dongle.
#
# The exchange is a small transaction on HID report 0x04. The host sends a
# start frame, then the command, then an end frame, and every step is
# acknowledged in byte 2 of the answer:
#     host ``00 00 01`` start  -> keyboard ``.. .. 01 ..``
#     host ``00 00 00 00 00 00 <command>`` -> the answer starts at byte 7
#     host ``00 00 02`` end    -> keyboard ``.. .. 02 ..``
#
# The command 0xAA asks whether the keyboard is online and 0x1A reads the
# level. Lofree's own web driver shows no charging state, so none is read.
#
# The command frame is 31 bytes on the dongle and 63 bytes on the cable.
# ----------------------------------------------------------------------

LOFREE_USAGE_PAGE = 0xFF1C
LOFREE_USAGE = 0x0092

LOFREE_REPORT_ID = 0x04
LOFREE_FRAME = 31

LOFREE_START = 0x01
LOFREE_END = 0x02
LOFREE_CMD_ONLINE = 0xAA
LOFREE_CMD_BATTERY = 0x1A

# The answer of a command starts here, counted from the report id.
LOFREE_DATA_AT = 7


def _lofree_frame(step: int) -> bytes:
    """Builds one of the two framing frames of the Lofree transaction."""
    frame = bytearray(LOFREE_FRAME)
    frame[0] = LOFREE_REPORT_ID
    frame[3] = step
    return bytes(frame)


def _lofree_command(command: int) -> bytes:
    """Builds the frame that carries a Lofree command."""
    frame = bytearray(LOFREE_FRAME)
    frame[0] = LOFREE_REPORT_ID
    frame[3] = command
    return bytes(frame)


def _lofree_payload(data: bytes) -> bytes | None:
    """The bytes behind the report id of a Lofree answer."""
    if len(data) < 2 or data[0] != LOFREE_REPORT_ID:
        return None
    return bytes(data[1:])


def _lofree_step(handle, step: int, timeout_ms: int = 600) -> bytes | None:
    """Sends one step of the transaction and waits for its acknowledgement."""
    try:
        handle.write(_lofree_frame(step))
    except OSError as exc:
        raise VendorError(f"写入失败：{exc}") from exc

    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        try:
            report = handle.read(LOFREE_FRAME, timeout_ms=80)
        except OSError:
            return None
        if not report:
            continue
        payload = _lofree_payload(bytes(report))
        if payload is None:
            continue
        if len(payload) >= 3 and payload[2] == step:
            return payload
    return None


def _lofree_command_answer(handle, command: int,
                           timeout_ms: int = 1200) -> bytes | None:
    """Runs the whole transaction and returns the answer of the command.

    The transaction is closed in any case, the way the web driver does it,
    so a failed read does not leave the keyboard in a half open state.
    """
    if _lofree_step(handle, LOFREE_START) is None:
        return None

    try:
        handle.write(_lofree_command(command))
    except OSError as exc:
        raise VendorError(f"写入失败：{exc}") from exc

    answer = None
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        try:
            report = handle.read(LOFREE_FRAME, timeout_ms=80)
        except OSError:
            break
        if not report:
            continue
        payload = _lofree_payload(bytes(report))
        if payload is None:
            continue
        # The answer echoes the command in byte 2, or answers with zero,
        # and it starts at the data offset.
        if (len(payload) > LOFREE_DATA_AT
                and payload[2] in (command, 0x00)
                and payload[4] == 0x00 and payload[5] == 0x00):
            answer = payload
            break

    _lofree_step(handle, LOFREE_END, timeout_ms=300)
    return answer


def _parse_lofree(payload: bytes) -> tuple[int, bool] | None:
    """Reads the level out of a Lofree answer."""
    if payload is None or len(payload) <= LOFREE_DATA_AT:
        return None
    percent = payload[LOFREE_DATA_AT]
    if not 0 <= percent <= 100:
        return None
    # The Lofree keyboards do not send a charge state.
    return percent, False


def _read_lofree(handle) -> tuple[int, bool] | None:
    """Reads the battery level over the Lofree transaction."""
    # The online command comes first, the way the web driver does it: a
    # keyboard that is off answers with zeros.
    online = _lofree_command_answer(handle, LOFREE_CMD_ONLINE)
    if online is None:
        return None
    if len(online) <= LOFREE_DATA_AT or online[LOFREE_DATA_AT] == 0:
        return None

    answer = _lofree_command_answer(handle, LOFREE_CMD_BATTERY)
    if answer is None:
        return None
    return _parse_lofree(answer)


# ----------------------------------------------------------------------
# NZXT — the Lift Elite mouse behind its dongle.
#
# The exchange is a 64 byte report that starts with 0x4E. The request asks
# the mouse behind the dongle for a property and the answer repeats the
# magic byte with a different command:
#     request ``4e 02 81 00 b0`` -> the telemetry property
#     answer  ``4e 02 97 00 01 ...``
#
# The level is at bytes 17 and 18, little endian, and the low bit of byte
# 22 is set while the mouse sits on its charging cable.
# ----------------------------------------------------------------------

NZXT_USAGE_PAGE = 0xFFCA
NZXT_USAGE = 0x0001

NZXT_MAGIC = 0x4E
NZXT_TARGET_MOUSE = 0x02
NZXT_OP_READ = 0x81
NZXT_PROP_TELEMETRY = 0xB0
NZXT_REPLY_TELEMETRY = 0x97
NZXT_ACK = 0xE5

NZXT_LEVEL_AT = 17
NZXT_CHARGING_AT = 22
NZXT_MIN_FRAME = 27


def _nzxt_request() -> bytes:
    """Builds the NZXT telemetry request."""
    frame = bytearray(64)
    frame[0] = NZXT_MAGIC
    frame[1] = NZXT_TARGET_MOUSE
    frame[2] = NZXT_OP_READ
    frame[4] = NZXT_PROP_TELEMETRY
    return bytes(frame)


def _parse_nzxt(data: bytes) -> tuple[int, bool] | None:
    """Reads the level out of an NZXT telemetry answer."""
    if len(data) < NZXT_MIN_FRAME:
        return None
    if (data[0] != NZXT_MAGIC or data[1] != NZXT_TARGET_MOUSE
            or data[2] != NZXT_REPLY_TELEMETRY):
        return None
    percent = data[NZXT_LEVEL_AT] | (data[NZXT_LEVEL_AT + 1] << 8)
    if not 0 <= percent <= 100:
        return None
    return percent, bool(data[NZXT_CHARGING_AT] & 0x01)


def _read_nzxt(handle) -> tuple[int, bool] | None:
    """Reads the battery level over the NZXT protocol."""
    _drain(handle, 64)
    _write(handle, _nzxt_request())

    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline:
        try:
            report = handle.read(64, timeout_ms=150)
        except OSError:
            return None
        if not report:
            continue
        data = bytes(report)
        if len(data) > 1 and data[0] == NZXT_MAGIC and data[1] == NZXT_ACK:
            # The dongle acknowledges the request first.
            continue
        parsed = _parse_nzxt(data)
        if parsed is not None:
            return parsed
    return None


# ----------------------------------------------------------------------
# ASUS ROG — the keyboard families that answer the ``12 01`` query.
#
# The exchange is the one g-helper uses for the ROG keyboards: a 65 byte
# output report that starts with the report id and the command family
# ``0x12``, answered by a report that echoes ``12 01``. The level sits in
# byte 6 and the charging flag in byte 9.
#
# The Falchion family is different: it reports a gauge from 0 to 10 in
# byte 6 and the real percentage in byte 11, so it needs its own offset.
# ----------------------------------------------------------------------

ASUS_USAGE_PAGE = 0xFF00

ASUS_CMD_POWER = 0x12
ASUS_SUB_POWER = 0x01

ASUS_LEVEL_AT = 6
ASUS_CHARGING_AT = 9
ASUS_FALCHION_LEVEL_AT = 11

# The Falchion family reports a gauge from 0 to 10 in byte 6 and the real
# percentage in byte 11, so it needs its own offset.
ASUS_FALCHION_PRODUCT_IDS = (0x193C, 0x193E, 0x1B04, 0x1B7E, 0x1C7D, 0x1A64)

# The ROG Omni receiver carries the keyboard on its own channel, where the
# packets start with the report id 0x02 instead of 0x00.
ASUS_OMNI_PRODUCT_ID = 0x1ACE
ASUS_OMNI_REPORT_ID = 0x02
ASUS_OMNI_PACKET_SIZE = 64

# The product ids of the ROG keyboards that answer the power query. The
# list keeps the protocol away from the ROG mice, which use their own
# collection and their own protocol.
ASUS_KEYBOARD_PRODUCT_IDS = (
    0x193C, 0x193E, 0x194B, 0x196B, 0x19FC, 0x19FE, 0x1A85, 0x1AAE,
    0x1AB3, 0x1AB5, 0x1ACE, 0x1B04, 0x1B30, 0x1B3A, 0x1B42, 0x1B78,
    0x1C60, 0x1CF1,
)

# The control channel of the receiver, which carries the pair list.
ASUS_OMNI_CONTROL_PAGE = 0xFF02

# The pair list of an Omni receiver names the devices that are plugged into
# it. The answer starts with the report id 0x01 and the command 0xA0, and
# every slot holds four bytes: the device id, little endian.
ASUS_OMNI_PAIRS_REPORT_ID = 0x01
ASUS_OMNI_PAIRS_COMMAND = 0xA0
ASUS_OMNI_PAIRS_AT = 5
ASUS_OMNI_SLOT = 4

# The keyboard ids that can be paired to an Omni receiver.
ASUS_OMNI_KEYBOARDS: dict[int, str] = {
    0x1A85: "ASUS ROG Azoth 键盘",
    0x1B42: "ASUS ROG Azoth Extreme 键盘",
    0x1CF1: "ASUS ROG Azoth Extreme SE 键盘",
    0x1AB0: "ASUS ROG Strix Scope II 96 键盘",
    0x1B7A: "ASUS ROG Strix Scope II 96 RX 键盘",
    0x1B06: "ASUS ROG Falchion RX 键盘",
    0x1CEA: "ASUS ROG Strix Morph 96 键盘",
}


def _asus_level_byte(product_id: int) -> int:
    """The byte that holds the level of an ASUS keyboard."""
    if product_id in ASUS_FALCHION_PRODUCT_IDS:
        return ASUS_FALCHION_LEVEL_AT
    return ASUS_LEVEL_AT


def _asus_request(report_id: int = 0x00) -> bytes:
    """Builds the ASUS keyboard power request."""
    frame = bytearray(65)
    frame[0] = report_id
    frame[1] = ASUS_CMD_POWER
    frame[2] = ASUS_SUB_POWER
    return bytes(frame)


def _asus_omni_pairs_request() -> bytes:
    """Builds the request for the pair list of an Omni receiver."""
    frame = bytearray(ASUS_OMNI_PACKET_SIZE)
    frame[0] = ASUS_OMNI_PAIRS_REPORT_ID
    frame[1] = ASUS_OMNI_PAIRS_COMMAND
    return bytes(frame)


def _parse_asus_pairs(data: bytes) -> list[int]:
    """The device ids that are paired to an Omni receiver."""
    if len(data) < 3:
        return []
    if data[0] == ASUS_OMNI_PAIRS_REPORT_ID:
        body = data
    elif data[0] == 0x00 and len(data) > 3 \
            and data[1] == ASUS_OMNI_PAIRS_REPORT_ID:
        body = data[1:]
    else:
        return []
    if body[1] != ASUS_OMNI_PAIRS_COMMAND:
        return []

    pids: list[int] = []
    for offset in range(ASUS_OMNI_PAIRS_AT, len(body) - 1, ASUS_OMNI_SLOT):
        pid = body[offset] | (body[offset + 1] << 8)
        if pid == 0:
            break
        pids.append(pid)
    return pids


def _read_asus_pairs(handle) -> list[int]:
    """Reads the pair list of an Omni receiver."""
    _drain(handle, ASUS_OMNI_PACKET_SIZE)
    _write(handle, _asus_omni_pairs_request())

    time.sleep(0.15)
    answer = _read_until(handle, ASUS_OMNI_PACKET_SIZE,
                         lambda data: bool(_parse_asus_pairs(data)),
                         timeout_ms=700)
    if answer is None:
        return []
    return _parse_asus_pairs(answer)


def _asus_omni_name(dev: dict) -> str | None:
    """The name of the keyboard that is paired to an Omni receiver.

    The pair list lives on the control channel of the receiver, which is a
    different collection from the keyboard channel. The name of the model
    comes from the pair list, because the receiver itself always reports
    the same product string.
    """
    product_id = dev.get("product_id")
    if product_id != ASUS_OMNI_PRODUCT_ID:
        return None

    # The control channel is the one on usage page 0xFF02.
    for candidate in hidsupport.enumerate_interfaces(0x0B05):
        if candidate.get("product_id") != product_id:
            continue
        if candidate.get("usage_page") != ASUS_OMNI_CONTROL_PAGE:
            continue
        try:
            handle = hid.device()
            handle.open_path(candidate.get("path", b""))
        except OSError:
            continue
        try:
            pids = _read_asus_pairs(handle)
        except (VendorError, OSError):
            continue
        finally:
            try:
                handle.close()
            except Exception:
                pass

        for pid in pids:
            name = ASUS_OMNI_KEYBOARDS.get(pid)
            if name is not None:
                return name
    return None


def _parse_asus(data: bytes, level_at: int = ASUS_LEVEL_AT) -> tuple[int, bool] | None:
    """Reads the level out of an ASUS keyboard answer.

    The answer echoes the command ``12 01``. hidapi leaves the report id
    out when it is zero and keeps it when it is not, so both shapes have to
    be read. The level and the charging flag are counted the way g-helper
    counts them, with the report id in front.
    """
    if len(data) < 2:
        return None

    # The offset of the report id: -1 when hidapi left it out, 0 when it is
    # still in front of the answer.
    if data[0] == ASUS_CMD_POWER and data[1] == ASUS_SUB_POWER:
        base = -1
    elif (len(data) > 2 and data[1] == ASUS_CMD_POWER
            and data[2] == ASUS_SUB_POWER):
        base = 0
    else:
        return None

    level_index = base + level_at
    charging_index = base + ASUS_CHARGING_AT
    if len(data) <= max(level_index, charging_index):
        return None

    percent = data[level_index]
    if percent > 100:
        return None
    charging = data[charging_index] != 0
    # A level of zero without charging means the keyboard is asleep.
    if percent == 0 and not charging:
        return None
    return percent, charging


def _read_asus(handle, level_at: int = ASUS_LEVEL_AT,
               report_id: int = 0x00, length: int = 65) -> tuple[int, bool] | None:
    """Reads the battery level over the ASUS keyboard protocol."""
    _drain(handle, length)
    frame = bytearray(length)
    frame[0] = report_id
    frame[1] = ASUS_CMD_POWER
    frame[2] = ASUS_SUB_POWER
    _write(handle, bytes(frame))

    time.sleep(0.15)
    answer = _read_until(handle, length,
                         lambda data: _parse_asus(data, level_at) is not None,
                         timeout_ms=700)
    if answer is None:
        return None
    return _parse_asus(answer, level_at)


# ----------------------------------------------------------------------
# The standard HID battery page — the fallback for every device that
# exposes usage page 0x06 / usage 0x20.
# ----------------------------------------------------------------------

STANDARD_USAGE_PAGE = 0x0006
STANDARD_USAGE = 0x0020


def _read_standard(handle) -> tuple[int, bool] | None:
    """Reads the level from the standard HID battery page."""
    try:
        answer = bytes(handle.get_feature_report(0, 2))
    except OSError as exc:
        raise VendorError(f"读取失败：{exc}") from exc
    if len(answer) < 2:
        return None
    percent = answer[1]
    if percent > 100:
        return None
    return percent, False


# ----------------------------------------------------------------------
# The protocol table
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class Protocol:
    """One vendor protocol."""

    name: str
    vendor_ids: tuple[int, ...]
    usage_page: int
    usage: int | None = None
    # How the request is sent: "output" writes an output report, "feature"
    # uses a feature report and "push" only listens.
    mode: str = "output"
    # The length of the frame that is read back.
    length: int = 64
    # The product ids the protocol is limited to. An empty tuple means that
    # every product id of the vendor is accepted.
    product_ids: tuple[int, ...] = ()
    connection: str = "2.4G"
    # The protocols with a low number are tried first.
    priority: int = 50
    # The number of bytes that are read back. Reading more than the report
    # is long is safe: the device only sends what it has.
    read_length: int = 64


PROTOCOLS: tuple[Protocol, ...] = (
    # The AULA keyboards come first: they share their usage page with the
    # Compx mice, and the keyboard frames are the ones that answer.
    Protocol(name="AULA 2.4G", vendor_ids=(0x3554,),
             usage_page=AULA_USAGE_PAGE, mode="output", length=20,
             read_length=64,
             product_ids=(0xFA08, 0xFA09, 0xFA0A, 0xFA10, 0xFA60),
             priority=10),
    Protocol(name="Compx 2.4G", vendor_ids=(0x260D, 0x33E4, 0x1D57, 0x3710),
             usage_page=COMPX_USAGE_PAGE, mode="output", length=17,
             read_length=17, priority=20),
    Protocol(name="Keychron 2.4G", vendor_ids=(0x3434,),
             usage_page=KEYCHRON_USAGE_PAGE, mode="output", length=64,
             read_length=64, priority=30),
    Protocol(name="Pulsar XS-1", vendor_ids=(0x3710,),
             usage_page=PULSAR_XS1_USAGE_PAGE, usage=PULSAR_XS1_USAGE,
             mode="feature", length=1 + PULSAR_XS1_FRAME,
             read_length=1 + PULSAR_XS1_FRAME, priority=35),
    Protocol(name="MCHOSE 2.4G", vendor_ids=(0x3837, 0x5253),
             usage_page=MCHOSE_USAGE_PAGE, usage=MCHOSE_USAGE,
             mode="feature", length=1 + MCHOSE_PAYLOAD,
             read_length=1 + MCHOSE_PAYLOAD, priority=40),
    Protocol(name="Lamzu 2.4G", vendor_ids=(0x373E, 0x37B0),
             usage_page=LAMZU_USAGE_PAGE, mode="feature", length=65,
             read_length=65, priority=42),
    Protocol(name="Ninjutso 2.4G", vendor_ids=(0x1915,),
             usage_page=NINJUTSO_USAGE_PAGE, mode="feature", length=32,
             read_length=32, priority=44),
    Protocol(name="Bloody 2.4G", vendor_ids=(0x1956,),
             usage_page=BLOODY_USAGE_PAGE, mode="feature", length=8,
             read_length=8, priority=46),
    Protocol(name="HyperX 2.4G", vendor_ids=(0x03F0, 0x0951),
             usage_page=HYPERX_USAGE_PAGE, mode="output", length=20,
             read_length=32, priority=48),
    Protocol(name="SteelSeries Nova", vendor_ids=(0x1038,),
             usage_page=STEELSERIES_USAGE_PAGE, mode="output", length=64,
             read_length=64,
             product_ids=tuple(STEELSERIES_NOVA), priority=50),
    Protocol(name="SteelSeries 耳机", vendor_ids=(0x1038,),
             usage_page=STEELSERIES_USAGE_PAGE, mode="output", length=31,
             read_length=31,
             product_ids=tuple(STEELSERIES_LEGACY), priority=52),
    Protocol(name="雷柏 2.4G", vendor_ids=(0x24AE,),
             usage_page=RAPOO_USAGE_PAGE, mode="push", length=19,
             read_length=19, priority=54),
    Protocol(name="Attack Shark 2.4G", vendor_ids=(0x1D57,),
             usage_page=ATTACK_SHARK_USAGE_PAGE, mode="push", length=8,
             read_length=8, priority=56),
    Protocol(name="Lofree 2.4G", vendor_ids=(0x388D,),
             usage_page=LOFREE_USAGE_PAGE, usage=LOFREE_USAGE,
             mode="output", length=LOFREE_FRAME, read_length=LOFREE_FRAME,
             priority=58),
    Protocol(name="NZXT 2.4G", vendor_ids=(0x1E71,),
             usage_page=NZXT_USAGE_PAGE, usage=NZXT_USAGE,
             mode="output", length=64, read_length=64, priority=60),
    Protocol(name="ASUS ROG 键盘", vendor_ids=(0x0B05,),
             usage_page=ASUS_USAGE_PAGE, mode="output", length=65,
             read_length=65, product_ids=ASUS_KEYBOARD_PRODUCT_IDS,
             priority=62),
    Protocol(name="HID 标准电池", vendor_ids=(),
             usage_page=STANDARD_USAGE_PAGE, usage=STANDARD_USAGE,
             mode="feature", length=2, read_length=2, connection="USB",
             priority=90),
)


def _read_steelseries(handle, product_id: int) -> tuple[int, bool] | None:
    """Reads the level of a SteelSeries device, whatever its family."""
    if product_id in STEELSERIES_NOVA:
        return _read_steelseries_nova(handle, STEELSERIES_NOVA[product_id])
    spec = STEELSERIES_LEGACY.get(product_id)
    if spec is None:
        return None
    return _read_steelseries_legacy(handle, spec)


def _read_protocol(protocol: Protocol, handle,
                    product_id: int) -> tuple[int, bool] | None:
    """Reads the level over one protocol."""
    if protocol.name == "AULA 2.4G":
        return _read_aula(handle)
    if protocol.name == "Compx 2.4G":
        return _read_compx(handle)
    if protocol.name == "Keychron 2.4G":
        return _read_keychron(handle)
    if protocol.name == "Pulsar XS-1":
        return _read_pulsar_xs1(handle)
    if protocol.name == "MCHOSE 2.4G":
        return _read_mchose(handle)
    if protocol.name == "Lamzu 2.4G":
        return _read_lamzu(handle)
    if protocol.name == "Ninjutso 2.4G":
        return _read_ninjutso(handle)
    if protocol.name == "Bloody 2.4G":
        return _read_bloody(handle)
    if protocol.name == "HyperX 2.4G":
        return _read_hyperx(handle)
    if protocol.name.startswith("SteelSeries"):
        return _read_steelseries(handle, product_id)
    if protocol.name == "雷柏 2.4G":
        return _read_rapoo(handle, protocol.read_length)
    if protocol.name == "Attack Shark 2.4G":
        return _read_attack_shark(handle, protocol.read_length)
    if protocol.name == "Lofree 2.4G":
        return _read_lofree(handle)
    if protocol.name == "NZXT 2.4G":
        return _read_nzxt(handle)
    if protocol.name == "ASUS ROG 键盘":
        if product_id == ASUS_OMNI_PRODUCT_ID:
            # The Omni receiver carries the keyboard on its own channel.
            return _read_asus(handle, _asus_level_byte(product_id),
                              report_id=ASUS_OMNI_REPORT_ID,
                              length=ASUS_OMNI_PACKET_SIZE)
        return _read_asus(handle, _asus_level_byte(product_id))
    return _read_standard(handle)


# ----------------------------------------------------------------------
# Reading the devices
# ----------------------------------------------------------------------

def _device_name(dev: dict, protocol: Protocol) -> str:
    """The name to show for a device.

    The model table is consulted first, because a receiver reports the same
    product string for every device that is paired with it.
    """
    vendor_id = dev.get("vendor_id", 0)
    product_id = dev.get("product_id", 0)
    model = devices.lookup(vendor_id, product_id)
    if model is not None:
        return model.name
    name = dev.get("product_string") or ""
    if name.lower() in ("usb receiver", "2.4g receiver", "receiver",
                         "wireless receiver", "2.4ghz receiver"):
        return f"{protocol.name} 接收器"
    return name or f"{protocol.name} 设备 {product_id:04X}"


def _device_kind(dev: dict, name: str) -> str:
    """The kind of the device, taken from the model table when possible."""
    model = devices.lookup(dev.get("vendor_id", 0), dev.get("product_id", 0))
    if model is not None:
        return model.kind
    lowered = name.lower()
    if any(word in lowered for word in ("keyboard", "keys", "keychron",
                                        "k98", "tkl", "ninx", "键盘")):
        return "keyboard"
    if any(word in lowered for word in ("headset", "headphone", "earphone",
                                        "cloud", "arctis", "nova", "bud",
                                        "耳机")):
        return "headset"
    if "controller" in lowered or "gamepad" in lowered or "手柄" in lowered:
        return "controller"
    return "mouse"


def _candidate_interfaces() -> list[tuple[dict, Protocol]]:
    """Every (interface, protocol) pair that could be asked.

    The protocols are sorted by their priority, so the more specific one
    gets the first chance on an interface that several of them match.
    """
    result: list[tuple[dict, Protocol]] = []
    seen: set[tuple[int, int, int]] = set()
    for dev in hidsupport.enumerate_interfaces():
        vendor_id = dev.get("vendor_id")
        product_id = dev.get("product_id", 0)
        page = dev.get("usage_page")
        if not isinstance(page, int) or not isinstance(vendor_id, int):
            continue
        for protocol in PROTOCOLS:
            if protocol.vendor_ids and vendor_id not in protocol.vendor_ids:
                continue
            if page != protocol.usage_page:
                continue
            if protocol.usage is not None:
                usage = dev.get("usage")
                if isinstance(usage, int) and usage != protocol.usage:
                    continue
            if protocol.product_ids and product_id not in protocol.product_ids:
                continue
            path = _path_text(dev.get("path", "")).lower()
            key = (vendor_id, product_id, hash(path))
            if key in seen:
                continue
            seen.add(key)
            result.append((dev, protocol))
    result.sort(key=lambda pair: pair[1].priority)
    return result


def read_devices() -> list[VendorDevice]:
    """Reads every device that answers one of the documented protocols."""
    found: list[VendorDevice] = []
    seen_names: set[str] = set()

    for dev, protocol in _candidate_interfaces():
        path = dev.get("path", "")
        try:
            handle = hid.device()
            handle.open_path(path)
        except OSError:
            continue

        try:
            parsed = _read_protocol(protocol, handle, dev.get("product_id", 0))
        except VendorError:
            continue
        except OSError:
            continue
        finally:
            try:
                handle.close()
            except Exception:
                pass

        if parsed is None:
            continue
        percent, charging = parsed
        if percent <= 0:
            continue

        name = _device_name(dev, protocol)

        # The Omni receiver answers for every keyboard that is plugged into
        # it, so its pair list is asked for the name of the device. Without a
        # keyboard behind it the receiver only serves a mouse, and that one
        # is read by the mouse driver.
        if dev.get("product_id") == ASUS_OMNI_PRODUCT_ID:
            paired = _asus_omni_name(dev)
            if paired is None:
                continue
            name = paired

        key = name.lower()
        if key in seen_names:
            continue
        seen_names.add(key)

        found.append(VendorDevice(
            name=name,
            percent=percent,
            charging=charging,
            kind=_device_kind(dev, name),
            connection=protocol.connection,
            product_id=dev.get("product_id", 0),
            vendor_id=dev.get("vendor_id", 0),
            protocol=protocol.name,
        ))
    return found
