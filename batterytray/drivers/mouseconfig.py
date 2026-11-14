"""Mouse settings: DPI, polling rate, DPI stages and button mapping.

The Razer feature report protocol is shared with the battery query, so this
module reuses the transport from :mod:`batterytray.drivers.razer` and only
adds the command groups that change the mouse configuration.

Command groups used here (class/id, as documented by OpenRazer):

===========  ==================================  ==========================
class/id     meaning                             arguments
===========  ==================================  ==========================
``04/05``    set DPI (x/y)                      storage, x_hi, x_lo,
                                                 y_hi, y_lo, 0, 0
``04/85``    get DPI (x/y)                      storage
``04/06``    set DPI stages                     1, active, count,
                                                 count x 7-byte records
``04/86``    get DPI stages                     1
``00/40``    set polling rate (HyperPolling)    storage, code
``00/C0``    get polling rate (HyperPolling)    -
``02/84``    list the button ids                -
``02/8C``    get the button mapping             profile, key, layer
``02/0C``    set the button mapping             profile, key, layer, fn,
                                                 len, data
===========  ==================================  ==========================

Two details bite every implementation:

* The transaction id is **not** the same for every command. Reading the DPI
  uses ``0x1F`` while writing it uses ``0x3F``; the polling rate uses
  ``0x1F`` for both directions.
* A setting has to be written twice: once for the active profile
  (``storage = 0x00``) and once for the onboard memory (``storage = 0x01``).
  Writing only the active profile makes the change disappear when the mouse
  is reconnected.

References:
    openrazer/openrazer            - driver/razerchromacommon.c
    1972863663/Viper-Control-Lite  - verified on the Viper V3 Pro
    uncoil protocol notes           - https://uncoil.justinthevoid.com/docs/protocol/
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .razer import (
    FEATURE_REPORT_LENGTH,
    RAZER_DEVICES,
    RAZER_VID,
    Status,
    USAGE_MOUSE,
    USAGE_PAGE_GENERIC_DESKTOP,
    _HidHandle,
    _crc_valid,
    _parse_report,
)

# Command classes.
CMD_CLASS_DEVICE = 0x00
CMD_CLASS_KEYMAPPING = 0x02
CMD_CLASS_DPI = 0x04

# Device control commands.
CMD_SET_POLLING_RATE = 0x40
CMD_GET_POLLING_RATE = 0xC0

# DPI commands.
CMD_SET_DPI = 0x05
CMD_SET_DPI_STAGES = 0x06
CMD_GET_DPI = 0x85
CMD_GET_DPI_STAGES = 0x86

# Button mapping commands.
CMD_LIST_BUTTONS = 0x84
CMD_GET_BUTTON_MAPPING = 0x8C
CMD_SET_BUTTON_MAPPING = 0x0C

# Transaction ids. The mouse answers on 0x1F, but the DPI write needs 0x3F.
TX_MOUSE = 0x1F
TX_DPI_WRITE = 0x3F

# The storage byte selects where a value is written.
STORAGE_ACTIVE = 0x00
STORAGE_ONBOARD = 0x01

# HyperPolling rate codes, as sent by OpenRazer and Synapse.
POLLING_RATE_CODES: dict[int, int] = {
    8000: 0x01,
    4000: 0x02,
    2000: 0x04,
    1000: 0x08,
    500: 0x10,
    250: 0x20,
    125: 0x40,
}
POLLING_CODE_RATES = {code: rate for rate, code in POLLING_RATE_CODES.items()}

# The rates the UI offers, slowest first.
SUPPORTED_POLLING_RATES = (125, 250, 500, 1000, 2000, 4000, 8000)

# The polling rates each connection mode actually supports.
#
# OpenRazer lists the wired Viper V3 Pro (``0x00C0``) at 125/500/1000 Hz
# and the wireless one (``0x00C1``) at 125..8000 Hz: the high rates need
# the HyperPolling dongle that ships with the mouse, and a plain cable tops
# out at 1000 Hz.
WIRED_POLLING_RATES = (125, 500, 1000)
WIRELESS_POLLING_RATES = (125, 500, 1000, 2000, 4000, 8000)

# The product ids that speak the HyperPolling protocol.
WIRELESS_PRODUCT_IDS = frozenset({
    0x00C1,  # Razer Viper V3 Pro Wireless
    0x00B3,  # Razer Hyperpolling Wireless Dongle
    0x00B8,  # Razer Viper V3 Hyperspeed
    0x0091,  # Razer Viper 8K
})

# The mouse accepts 100..35000 DPI; the usual picks are offered in the UI.
MIN_DPI = 100
MAX_DPI = 35000

# A mouse has at most five DPI stages.
MAX_DPI_STAGES = 5

# A wireless mouse stops answering a few seconds after the last movement.
# The dongle still enumerates, so the device looks connected while every
# command comes back with status 0x04 (timeout).
SLEEP_STATUS = 0x04


class MouseConfigError(RuntimeError):
    """Raised when the mouse rejects a command or cannot be reached."""


class MouseAsleepError(MouseConfigError):
    """Raised when the mouse did not answer because it went to sleep.

    A wireless mouse stops answering the dongle a few seconds after the last
    movement, even though the dongle still enumerates and the mouse still
    looks connected. Every command comes back with status ``0x04``.

    This is not a failure of the command, so the caller can retry once the
    user moves the mouse again.
    """


@dataclass(frozen=True)
class DpiStage:
    """One DPI stage stored on the mouse."""

    dpi: int
    active: bool = False

    def __post_init__(self) -> None:
        if not MIN_DPI <= self.dpi <= MAX_DPI:
            raise ValueError(f"DPI 必须在 {MIN_DPI}–{MAX_DPI} 之间")


@dataclass
class MouseSettings:
    """The settings read from (or written to) a mouse."""

    dpi_x: int = 0
    dpi_y: int = 0
    onboard_dpi_x: int = 0
    onboard_dpi_y: int = 0
    polling_rate: int = 0
    stages: list[DpiStage] = field(default_factory=list)
    # The stage the DPI button starts on, counted from zero.
    active_stage: int = 0

    @property
    def has_stages(self) -> bool:
        """Whether the mouse stores DPI stages."""
        return bool(self.stages)


# The function id that means "emit the click of the mouse button in the
# data bytes".
#
# A factory default mapping is written as function id 1 with the button id
# in the data bytes. The mouse then uses its own built-in behaviour for that
# button, which is how Synapse stores an untouched button.
FUNCTION_DEFAULT = 1

# The function id that turns a button off entirely.
FUNCTION_NONE = 0

# The mouse button codes that can be assigned to a button. These are the
# values the data bytes of function id 1 carry, and they are the same ids
# the mouse uses for its own buttons.
ASSIGNABLE_BUTTON_CODES: dict[int, str] = {
    1: "左键",
    2: "右键",
    3: "中键",
    4: "后退键",
    5: "前进键",
    9: "滚轮上",
    10: "滚轮下",
    104: "左倾",
    105: "右倾",
}

# The values the mouse is set to when its configuration is restored.
#
# Neither protocol has a "factory reset" command, so the defaults are
# written like any other setting: the buttons go back to their built-in
# behaviour, the polling rate and the DPI go to these values and the DPI
# stages are replaced by this list.
DEFAULT_DPI = 1600
DEFAULT_POLLING_RATE = 1000
DEFAULT_STAGES: tuple[int, ...] = (400, 800, 1600)


def default_button_mapping(button_id: int) -> tuple[int, bytes]:
    """The factory default mapping of a mouse button.

    The mouse stores an untouched button as function id 1 with the button id
    in the data bytes, which tells the firmware to keep the built-in
    behaviour of that button. Writing this back is what "reset to default"
    means.

    Returns the function id and the data bytes to write.
    """
    return FUNCTION_DEFAULT, bytes([button_id])


# The function ids of a mouse button mapping, as listed in Synapse's
# ``fnIdEnum``. The names come from the protocol documentation, which lists
# them as read back from the hardware.
#
# The ids that carry a payload in the data bytes are the ones worth
# offering: the mouse button codes, the DPI button, the profile button, the
# scroll mode and the turbo mode. The remaining ids are macro slots and
# key codes, which need a payload this program does not build.
BUTTON_FUNCTIONS: dict[int, str] = {
    0: "无操作",
    1: "鼠标按键",
    6: "DPI 切换",
    7: "配置文件切换",
    11: "双击",
    14: "连发（Turbo）",
    18: "滚轮模式",
}

@dataclass(frozen=True)
class ButtonMapping:
    """The function assigned to one mouse button."""

    button_id: int
    function_id: int
    # The extra payload a function carries, e.g. the interval of a turbo key.
    data: bytes = b""

    @property
    def label(self) -> str:
        """A readable name for the assigned function."""
        if self.function_id == FUNCTION_DEFAULT and self.data:
            code = self.data[0]
            return ASSIGNABLE_BUTTON_CODES.get(code, f"鼠标按键 {code}")
        return BUTTON_FUNCTIONS.get(self.function_id, f"功能 {self.function_id}")

    @property
    def is_default(self) -> bool:
        """Whether the button still has its factory default function.

        The mouse stores an untouched button as function id 1 with the
        button id in the data bytes, so both parts have to match.
        """
        function_id, data = default_button_mapping(self.button_id)
        return self.function_id == function_id and self.data[:1] == data


# The button ids of a Razer mouse, as listed by command 02/84.
#
# A Viper V3 Pro answers ``08 01 02 03 04 05 60 09 0A``, so the mouse has
# eight buttons: the five main ones, the DPI key (0x60) and the wheel.
MOUSE_BUTTON_IDS: dict[int, str] = {
    1: "左键",
    2: "右键",
    3: "滚轮中键",
    4: "后退键",
    5: "前进键",
    9: "滚轮上",
    10: "滚轮下",
    11: "侧键 1",
    12: "侧键 2",
    13: "侧键 3",
    14: "侧键 4",
    15: "侧键 5",
    16: "侧键 6",
    52: "左倾",
    53: "右倾",
    96: "DPI 键",
    106: "滚轮模式键",
}


def _build_request(transaction_id: int, command_class: int, command_id: int,
                   arguments: bytes = b"", data_size: int | None = None) -> bytes:
    """Builds a Razer feature report request with a valid CRC.

    ``data_size`` defaults to the number of argument bytes, which is what
    OpenRazer sends for the mouse commands.
    """
    if len(arguments) > 80:
        raise ValueError("Razer 报告参数不能超过 80 字节")

    buf = bytearray(FEATURE_REPORT_LENGTH)
    buf[1] = Status.NEW
    buf[2] = transaction_id
    buf[6] = len(arguments) if data_size is None else data_size
    buf[7] = command_class
    buf[8] = command_id
    buf[9:9 + len(arguments)] = arguments
    crc = 0
    for i in range(3, 89):
        crc ^= buf[i]
    buf[89] = crc
    return bytes(buf)


def _query(handle: _HidHandle, transaction_id: int, command_class: int,
           command_id: int, arguments: bytes = b"",
           data_size: int | None = None,
           retries: tuple[int, ...] = (80, 150, 250, 500)) -> bytes | None:
    """Sends one command and returns the raw response, or ``None``.

    The dongle needs time to complete its 2.4 GHz round trip, so each attempt
    waits longer than the last. Only ``status == 0x02`` counts as success;
    ``0x01`` means busy and triggers another attempt.

    The response has to echo the command that was sent. The dongle has a
    single reply slot, so when Synapse talks to the same mouse its answer
    can show up here instead of ours; that answer is discarded and the
    command is sent again.

    A status of ``0x04`` means the mouse is asleep. It is not retried,
    because waiting longer does not wake a sleeping mouse up.
    """
    request = _build_request(transaction_id, command_class, command_id,
                             arguments, data_size)
    for sleep_ms in retries:
        if not handle.set_feature(request):
            return None
        time.sleep(sleep_ms / 1000)
        response = handle.get_feature(FEATURE_REPORT_LENGTH)
        if response is None or len(response) < FEATURE_REPORT_LENGTH:
            continue
        status, resp_class, resp_id = _parse_report(response)
        if status == Status.SUCCESSFUL:
            # Only trust a reply that answers the command we sent.
            if resp_class == command_class and resp_id == command_id:
                return response
            time.sleep(0.03)
            continue
        if status == Status.BUSY:
            continue
        if status == Status.TIMEOUT:
            # The mouse is asleep; a longer wait would not help.
            raise MouseAsleepError("鼠标处于休眠状态，请移动鼠标后重试")
        return None
    return None


def _query_checked(handle: _HidHandle, transaction_id: int,
                   command_class: int, command_id: int, arguments: bytes = b"",
                   data_size: int | None = None, label: str = "命令") -> bytes:
    """Sends one command and raises when the mouse does not answer."""
    response = _query(handle, transaction_id, command_class, command_id,
                      arguments, data_size)
    if response is None:
        raise MouseConfigError(f"{label}失败：鼠标没有响应")
    if not _crc_valid(response):
        raise MouseConfigError(f"{label}失败：响应校验和不正确")
    return response


def _candidate_interfaces() -> list[dict]:
    """Lists the HID interfaces that can carry mouse configuration commands."""
    import hid

    candidates = []
    for dev in hid.enumerate(RAZER_VID):
        is_mouse = (dev["usage_page"] == USAGE_PAGE_GENERIC_DESKTOP
                    and dev["usage"] == USAGE_MOUSE)
        if not is_mouse:
            continue
        candidates.append(dev)
    # Interface 0 is the one OpenRazer sends the mouse commands to.
    candidates.sort(key=lambda d: (d["interface_number"], d["product_id"]))
    return candidates


def _device_name(product_id: int, product_string: str) -> str:
    known = RAZER_DEVICES.get(product_id)
    if known:
        return known[0]
    return product_string or f"Razer Device {product_id:04X}"


class MouseController:
    """Reads and writes the configuration of one Razer mouse."""

    def __init__(self, path: str, product_id: int, name: str):
        self.path = path
        self.product_id = product_id
        self.name = name
        self._handle = _HidHandle(path)

    @property
    def supported_polling_rates(self) -> tuple[int, ...]:
        """The polling rates this mouse and connection mode support.

        A wired Viper V3 Pro tops out at 1000 Hz; the wireless one reaches
        8000 Hz through the HyperPolling dongle. Offering a rate the mouse
        cannot use makes the firmware silently ignore the write, so the UI
        only shows what the hardware actually accepts.
        """
        if self.product_id in WIRELESS_PRODUCT_IDS:
            return WIRELESS_POLLING_RATES
        return WIRED_POLLING_RATES

    def close(self) -> None:
        """Releases the HID handle."""
        try:
            self._handle.close()
        except Exception:
            pass

    def __enter__(self) -> "MouseController":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # DPI
    # ------------------------------------------------------------------

    def get_dpi(self, storage: int = STORAGE_ACTIVE) -> tuple[int, int]:
        """Reads the x/y DPI from the given storage."""
        response = _query_checked(
            self._handle, TX_MOUSE, CMD_CLASS_DPI, CMD_GET_DPI,
            bytes([storage]), data_size=0x07, label="读取 DPI")
        dpi_x = (response[10] << 8) | response[11]
        dpi_y = (response[12] << 8) | response[13]
        return dpi_x, dpi_y

    def set_dpi(self, dpi: int, include_onboard: bool = True) -> None:
        """Writes the x/y DPI to the active profile and the onboard memory.

        The mouse needs the active profile (``0x00``) and the onboard memory
        (``0x01``) to be written separately; writing only one of them makes
        the change disappear after a reconnect.
        """
        if not MIN_DPI <= dpi <= MAX_DPI:
            raise ValueError(f"DPI 必须在 {MIN_DPI}–{MAX_DPI} 之间")

        high, low = divmod(dpi, 256)
        storages = (STORAGE_ACTIVE, STORAGE_ONBOARD) if include_onboard \
            else (STORAGE_ACTIVE,)
        for storage in storages:
            arguments = bytes([storage, high, low, high, low, 0x00, 0x00])
            # The DPI write uses a different transaction id than the read.
            _query_checked(self._handle, TX_DPI_WRITE, CMD_CLASS_DPI,
                           CMD_SET_DPI, arguments, data_size=0x07,
                           label=f"写入 {dpi} DPI（存储 {storage}）")

    # ------------------------------------------------------------------
    # Polling rate
    # ------------------------------------------------------------------

    def get_polling_rate(self) -> int:
        """Reads the polling rate in Hz."""
        response = _query_checked(
            self._handle, TX_MOUSE, CMD_CLASS_DEVICE, CMD_GET_POLLING_RATE,
            b"", label="读取回报率")
        code = response[10]
        if code not in POLLING_CODE_RATES:
            raise MouseConfigError(f"鼠标返回了未知的回报率代码 0x{code:02X}")
        return POLLING_CODE_RATES[code]

    def set_polling_rate(self, rate: int, include_onboard: bool = True) -> None:
        """Writes the polling rate to the active profile and onboard memory."""
        if rate not in POLLING_RATE_CODES:
            raise ValueError(f"不支持的回报率：{rate} Hz")
        supported = self.supported_polling_rates
        if rate not in supported:
            raise ValueError(
                f"当前连接方式不支持 {rate} Hz，可用："
                + "、".join(f"{r} Hz" for r in supported))

        code = POLLING_RATE_CODES[rate]
        storages = (STORAGE_ACTIVE, STORAGE_ONBOARD) if include_onboard \
            else (STORAGE_ACTIVE,)
        for storage in storages:
            _query_checked(self._handle, TX_MOUSE, CMD_CLASS_DEVICE,
                           CMD_SET_POLLING_RATE, bytes([storage, code]),
                           data_size=0x02,
                           label=f"写入 {rate} Hz（存储 {storage}）")

    # ------------------------------------------------------------------
    # DPI stages
    # ------------------------------------------------------------------

    def get_stages(self) -> list[DpiStage]:
        """Reads the DPI stages stored on the mouse."""
        response = _query_checked(
            self._handle, TX_MOUSE, CMD_CLASS_DPI, CMD_GET_DPI_STAGES,
            bytes([0x01]), data_size=0x26, label="读取 DPI 挡位")
        count = response[11]
        stages: list[DpiStage] = []
        for index in range(min(count, MAX_DPI_STAGES)):
            offset = 12 + index * 7
            if offset + 4 > len(response):
                break
            dpi = (response[offset + 1] << 8) | response[offset + 2]
            if dpi <= 0:
                continue
            stages.append(DpiStage(dpi=dpi))
        return stages

    def set_stages(self, stages: list[DpiStage],
                   active_index: int = 0) -> None:
        """Writes the DPI stages to the onboard memory.

        The mouse stores at most five stages. ``active_index`` is zero based
        and selects the stage the DPI button switches to.
        """
        if not stages:
            raise ValueError("至少需要一个 DPI 挡位")
        if len(stages) > MAX_DPI_STAGES:
            raise ValueError(f"最多只能设置 {MAX_DPI_STAGES} 个 DPI 挡位")
        if not 0 <= active_index < len(stages):
            raise ValueError("当前挡位超出了挡位范围")

        arguments = bytearray([0x01, active_index + 1, len(stages)])
        for index, stage in enumerate(stages):
            high, low = divmod(stage.dpi, 256)
            arguments.extend([index, high, low, high, low, 0x00, 0x00])
        _query_checked(self._handle, TX_MOUSE, CMD_CLASS_DPI,
                       CMD_SET_DPI_STAGES, bytes(arguments), data_size=0x26,
                       label="写入 DPI 挡位")

    # ------------------------------------------------------------------
    # Button mapping
    # ------------------------------------------------------------------

    def list_buttons(self) -> list[int]:
        """Lists the button ids the mouse reports.

        The reply starts with the count in the first argument byte, followed
        by one id per button. On a Viper V3 Pro the answer reads
        ``08 01 02 03 04 05 60 09 0A``, so the count sits at offset 9 and
        the first button id at offset 10.
        """
        response = _query_checked(
            self._handle, TX_MOUSE, CMD_CLASS_KEYMAPPING, CMD_LIST_BUTTONS,
            b"", label="读取按键列表")
        count = response[9]
        buttons: list[int] = []
        for index in range(count):
            offset = 10 + index
            if offset >= len(response):
                break
            buttons.append(response[offset])
        return buttons

    def get_button_mapping(self, button_id: int,
                           layer: int = 0) -> ButtonMapping:
        """Reads the function assigned to a button.

        ``layer`` is 0 for the normal layer and 1 for Hypershift.

        The reply repeats the request and then the mapping. The bytes are
        ``profile, button id, layer, function id, length, data``. On a Viper
        V3 Pro the right click answers ``01 02 01 01 01 02 ...`` and a
        button that was changed to "browser back" answers
        ``01 05 00 2B 05 ...``, so the function id always sits at offset 12.
        """
        response = _query_checked(
            self._handle, TX_MOUSE, CMD_CLASS_KEYMAPPING,
            CMD_GET_BUTTON_MAPPING, bytes([0x01, button_id, layer]),
            data_size=0x0A, label=f"读取按键 {button_id} 的映射")
        function_id = response[12]
        length = min(response[13], 5)
        data = bytes(response[14:14 + length])
        return ButtonMapping(button_id=button_id, function_id=function_id,
                             data=data)

    def set_button_mapping(self, button_id: int, function_id: int,
                           layer: int = 0, data: bytes = b"") -> None:
        """Assigns a function to a button."""
        payload = data[:5].ljust(5, b"\x00")
        arguments = bytes([0x01, button_id, layer, function_id,
                           len(payload)]) + payload
        _query_checked(self._handle, TX_MOUSE, CMD_CLASS_KEYMAPPING,
                       CMD_SET_BUTTON_MAPPING, arguments, data_size=0x0A,
                       label=f"设置按键 {button_id} 的映射")

    def reset_button(self, button_id: int, layer: int = 0) -> None:
        """Restores one button to its factory default.

        The mouse has no "reset keymap" command; the factory default is
        written like any other mapping, as function id 1 with the button id
        in the data bytes. The firmware then goes back to its own built-in
        behaviour for that button.
        """
        function_id, data = default_button_mapping(button_id)
        self.set_button_mapping(button_id, function_id, layer, data)

    def assign_button_code(self, button_id: int, code: int,
                           layer: int = 0) -> None:
        """Makes a button emit the click of another mouse button.

        The click is written as function id 1 with the wanted button code
        in the data bytes, which is what Synapse calls a "mouse function".
        """
        self.set_button_mapping(button_id, FUNCTION_DEFAULT, layer,
                                bytes([code]))

    def reset_all_buttons(self, layer: int = 0) -> None:
        """Restores every button to its factory default."""
        for button_id in self.list_buttons():
            self.reset_button(button_id, layer)

    def reset_to_factory(self, layer: int = 0) -> None:
        """Restores the whole configuration of the mouse.

        The protocol has no "factory reset" command, so every part of the
        configuration is written back separately: the buttons go to their
        built-in behaviour, the DPI stages are replaced by the default
        ones, and the polling rate and the DPI go to their defaults.

        The order matters. Writing the DPI stages makes the stage at
        ``active_index`` the active one, so the stages have to go before
        the DPI, which then overrules the stage.
        """
        self.reset_all_buttons(layer)
        self.set_stages([DpiStage(dpi=dpi) for dpi in DEFAULT_STAGES], 0)
        self.set_polling_rate(DEFAULT_POLLING_RATE)
        self.set_dpi(DEFAULT_DPI)

    # ------------------------------------------------------------------
    # High level helpers
    # ------------------------------------------------------------------

    def get_settings(self) -> MouseSettings:
        """Reads every setting the mouse exposes.

        A mouse that does not answer one particular getter still reports the
        other values. A sleeping mouse raises instead, because none of the
        values would be trustworthy.
        """
        dpi_x, dpi_y = self.get_dpi(STORAGE_ACTIVE)
        try:
            onboard_x, onboard_y = self.get_dpi(STORAGE_ONBOARD)
        except MouseAsleepError:
            raise
        except MouseConfigError:
            onboard_x, onboard_y = 0, 0
        try:
            polling = self.get_polling_rate()
        except MouseAsleepError:
            raise
        except MouseConfigError:
            polling = 0
        try:
            stages = self.get_stages()
        except MouseAsleepError:
            raise
        except MouseConfigError:
            stages = []
        return MouseSettings(dpi_x=dpi_x, dpi_y=dpi_y,
                             onboard_dpi_x=onboard_x, onboard_dpi_y=onboard_y,
                             polling_rate=polling, stages=stages)

    def apply_settings(self, dpi: int | None = None,
                       polling_rate: int | None = None,
                       stages: list[DpiStage] | None = None,
                       active_stage: int = 0) -> MouseSettings:
        """Writes the given settings and reads them back for verification.

        Every write is confirmed by reading the value again, so a mouse that
        silently refuses a command is reported instead of being assumed to
        have accepted it.

        The order matters. Writing the DPI stages makes the stage at
        ``active_stage`` the active one, so it overrules whatever DPI was
        written before it. The stages therefore go first and the DPI last,
        which makes the DPI the value the mouse actually ends up with.
        """
        if stages:
            self.set_stages(stages, active_stage)
        if polling_rate is not None:
            self.set_polling_rate(polling_rate)
        if dpi is not None:
            self.set_dpi(dpi)

        settings = self.get_settings()
        if dpi is not None and (settings.dpi_x != dpi or settings.dpi_y != dpi):
            raise MouseConfigError(
                f"DPI 写入后回读不一致：目标 {dpi}，实际 {settings.dpi_x}")
        if polling_rate is not None and settings.polling_rate != polling_rate:
            raise MouseConfigError(
                f"回报率写入后回读不一致：目标 {polling_rate}，"
                f"实际 {settings.polling_rate}")
        return settings


def open_mouse(product_id: int | None = None) -> MouseController | None:
    """Opens the first Razer mouse that answers, or returns ``None``.

    ``product_id`` narrows the search to one device; without it the first
    mouse that responds to the configuration commands is used.
    """
    errors: list[str] = []
    for dev in _candidate_interfaces():
        pid = dev["product_id"]
        if product_id is not None and pid != product_id:
            continue
        path = dev["path"]
        if isinstance(path, bytes):
            path = path.decode("utf-8", errors="replace")

        try:
            controller = MouseController(
                path, pid, _device_name(pid, dev.get("product_string") or ""))
        except OSError:
            continue

        # A mouse that does not answer the polling rate query is asleep or
        # not reachable; try the next interface.
        try:
            controller.get_polling_rate()
        except MouseAsleepError:
            controller.close()
            raise
        except MouseConfigError as exc:
            errors.append(f"PID 0x{pid:04X}: {exc}")
            controller.close()
            continue
        return controller

    if errors:
        raise MouseConfigError("找到鼠标但没有接口响应配置命令：\n"
                               + "\n".join(errors))
    return None
