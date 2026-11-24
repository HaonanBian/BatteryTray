"""Mouse settings for ASUS ROG mice.

The ASUS HID protocol is quite different from the Razer one. A packet is
64 bytes long and carries three header bytes:

===========  =====================================================
    byte       meaning
===========  =====================================================
``0``        the report id, ``0x00`` for a direct cable and
             ``0x03`` behind the ROG Omni receiver
``1``        the command family: ``0x12`` reads, ``0x51`` writes
             and ``0x50`` handles the profiles
``2``        the sub command
``3..``      the payload, padded with zeros
===========  =====================================================

Two details bite every implementation:

* Every write has to be followed by a save command
  (``report id, 0x50, 0x03``). Without it the mouse only echoes the
  packet back and the change is lost.
* The settings live in five onboard profiles. The read commands always
  report the active profile, so switching the profile changes what the
  mouse returns.

Only the USB connection can change settings. Over Bluetooth the mouse
still reports its battery level, but it ignores the configuration
commands.

References:
    seerge/g-helper              - the protocol implementation for
                                    30+ models, cross checked on hardware
    CalcProgrammer1/OpenRGB      - the VID/PID table and lighting commands
    kyokenn/hid-asus-mouse       - the Linux button driver, used to
                                    cross check the button codes
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import hid

from . import hidsupport

ASUS_VID = 0x0B05

# The product id of the mouse depends on the connection.
PRODUCT_WIRED = 0x1A66
PRODUCT_WIRELESS = 0x1A68
PRODUCT_BLUETOOTH = 0x1A6A
PRODUCT_OMNI_RECEIVER = 0x1ACE

# The product id of the ROG Omni receiver is the same for every mouse
# that plugs into it, so the name has to come from somewhere else.
ASUS_DEVICES: dict[int, str] = {
    PRODUCT_WIRED: "ROG Keris Wireless Aimpoint（有线）",
    PRODUCT_WIRELESS: "ROG Keris Wireless Aimpoint（2.4G）",
    PRODUCT_BLUETOOTH: "ROG Keris Wireless Aimpoint（蓝牙）",
    PRODUCT_OMNI_RECEIVER: "ROG Keris Wireless Aimpoint（Omni 接收器）",
}

# The control interface of the ASUS mice uses a vendor usage page.
USAGE_PAGE_VENDOR = 0xFF01

# The packet size of the ASUS protocol. The direct connection uses a
# 64-byte report plus the HID report id, the Omni receiver uses 64 bytes
# including the id. This mirrors g-helper's USBPacketSize().
PACKET_SIZE = 65
OMNI_PACKET_SIZE = 64

# The command families.
FAMILY_READ = 0x12
FAMILY_WRITE = 0x51
FAMILY_PROFILE = 0x50

# The sub commands.
SUB_DEVICE_INFO = 0x00
SUB_SETTING = 0x04
SUB_DPI_XY = 0x02
SUB_BUTTONS = 0x05
SUB_BATTERY = 0x07

# The sub command of the settings block that changes a value.
SUB_SET = 0x31
# The sub command that changes the button mapping.
SUB_SET_BUTTON = 0x21

# The DPI is stored in steps of 50, starting at 50.
DPI_INCREMENT = 50
MIN_DPI = 100
MAX_DPI = 36000

# The number of DPI stages and onboard profiles.
DPI_STAGE_COUNT = 4
PROFILE_COUNT = 5

# The polling rates the protocol knows, with their encoded values.
POLLING_RATES: dict[int, int] = {
    125: 0,
    250: 1,
    500: 2,
    1000: 3,
    2000: 4,
    4000: 5,
    8000: 6,
}

# The Keris Aimpoint only reaches 1000 Hz on its own receiver. The higher
# values need the special "booster" receiver, so they must not be offered
# in the dialog for this mouse.
SUPPORTED_POLLING_RATES: tuple[int, ...] = (125, 250, 500, 1000)

# The button slots of the mouse, with the source code the protocol uses.
#
# The numbers are the ASUS key codes, not the Razer ones. The slots are
# listed in the order the mouse reports them.
BUTTON_CODES: dict[int, str] = {
    0x01F0: "左键",
    0x01F1: "右键",
    0x01F2: "滚轮中键",
    0x01E3: "双击",
    0x01E4: "后退键",
    0x01E5: "前进键",
    0x01E6: "DPI 键",
    0x01E7: "目标锁定",
    0x01E8: "滚轮上",
    0x01E9: "滚轮下",
}

# The order the buttons are shown in.
BUTTON_ORDER: tuple[int, ...] = (
    0x01F0, 0x01F1, 0x01F2, 0x01E4, 0x01E5, 0x01E6, 0x01E8, 0x01E9,
)

# The action codes a button can be set to.
#
# The source code of a button doubles as its factory default, because the
# mouse then falls back to its own built-in behaviour for that button.
ACTION_CODES: dict[int, str] = {
    0x0000: "无操作",
    0x01F0: "左键",
    0x01F1: "右键",
    0x01F2: "滚轮中键",
    0x01E3: "双击",
    0x01E4: "后退键",
    0x01E5: "前进键",
    0x01E6: "DPI 切换",
    0x01E7: "目标锁定",
    0x01E8: "滚轮上",
    0x01E9: "滚轮下",
    0x01C0: "连发（切换）",
    0x01C1: "连发（按住）",
}

# The mouse button codes that can be assigned to a button.
ASSIGNABLE_BUTTON_CODES: dict[int, str] = {
    0x01F0: "左键",
    0x01F1: "右键",
    0x01F2: "滚轮中键",
    0x01E4: "后退键",
    0x01E5: "前进键",
    0x01E8: "滚轮上",
    0x01E9: "滚轮下",
}

# The action code that turns a button off.
ACTION_DISABLED = 0x0000

# The values the mouse is set to when its configuration is restored.
#
# Neither protocol has a "factory reset" command, so the defaults are
# written like any other setting.
DEFAULT_DPI = 1600
DEFAULT_POLLING_RATE = 1000
DEFAULT_STAGES: tuple[int, ...] = (400, 800, 1600)


class AsusMouseError(Exception):
    """A setting could not be read or written."""


class AsusMouseAsleep(AsusMouseError):
    """The mouse did not answer because it is asleep."""


@dataclass(frozen=True)
class AsusDpiStage:
    """One DPI stage of the mouse."""

    dpi_x: int
    dpi_y: int
    red: int = 0
    green: int = 0
    blue: int = 0


@dataclass
class AsusMouseSettings:
    """Everything the mouse reports about its configuration."""

    dpi_stages: list[AsusDpiStage] = field(default_factory=list)
    polling_rate: int = 0
    active_profile: int = 1
    active_dpi_stage: int = 1
    profile_count: int = PROFILE_COUNT
    battery: int = 0
    charging: bool = False
    angle_snapping: bool = False
    has_xy_dpi: bool = True


@dataclass(frozen=True)
class AsusButtonMapping:
    """The action assigned to one mouse button.

    The ASUS protocol stores an action code rather than a function id, so
    the two vendors use different words for the same thing.
    """

    button_id: int
    action_code: int

    @property
    def label(self) -> str:
        """A readable name for the assigned action."""
        return ACTION_CODES.get(self.action_code,
                                f"未知操作 0x{self.action_code:04X}")

    @property
    def is_default(self) -> bool:
        """Whether the button still has its factory default action.

        The mouse stores an untouched button with its own source code as
        the action, so the firmware keeps the built-in behaviour.
        """
        return self.action_code == self.button_id


def default_action_code(button_id: int) -> int:
    """The factory default action of a mouse button.

    The mouse stores an untouched button with its own source code as the
    action, so the firmware falls back to its built-in behaviour.
    """
    return button_id


def _build_packet(report_id: int, family: int, *args: int,
                  size: int = PACKET_SIZE) -> bytes:
    """Builds one protocol packet."""
    packet = bytearray(size)
    packet[0] = report_id
    packet[1] = family
    for i, value in enumerate(args):
        if 2 + i >= size:
            break
        packet[2 + i] = value & 0xFF
    return bytes(packet)


class AsusMouseController:
    """Reads and writes the configuration of one ASUS ROG mouse."""

    # The direct connection is the common case. The constructor overrides
    # this for the Omni receiver.
    packet_size = PACKET_SIZE

    def __init__(self, path: bytes | str, product_id: int, name: str,
                 report_id: int = 0x00):
        self.path = path
        self.product_id = product_id
        self.name = name
        self.report_id = report_id
        self.packet_size = _packet_size_for(product_id)
        self._handle: hid.device | None = None
        try:
            handle = hid.device()
            handle.open_path(path)
        except OSError as exc:
            raise AsusMouseError(f"无法打开鼠标：{exc}") from exc
        self._handle = handle

    # ------------------------------------------------------------------
    # Low level transport
    # ------------------------------------------------------------------

    def _discard_pending(self) -> None:
        """Drops reports that are already waiting in the input queue.

        The control interface also receives button and profile events. If
        one of them is still queued when a command is sent, the next read
        would return the event instead of the answer. Draining first keeps
        the command and the answer together.
        """
        if self._handle is None:
            return
        for _ in range(8):
            try:
                pending = self._handle.read(self.packet_size, timeout_ms=1)
            except OSError:
                return
            if not pending:
                return

    def _exchange(self, packet: bytes, label: str) -> bytes | None:
        """Sends a packet and waits for the matching answer.

        A read may return an event report before the answer. Such reports
        are skipped by comparing the header with the command that was
        sent, which is what g-helper does as well.
        """
        if self._handle is None:
            raise AsusMouseError("鼠标没有连接")

        self._discard_pending()
        try:
            self._handle.write(packet)
        except OSError as exc:
            raise AsusMouseError(f"{label}失败：{exc}") from exc

        empty = False
        for _ in range(25):
            time.sleep(0.02)
            try:
                answer = self._handle.read(self.packet_size, timeout_ms=50)
            except OSError as exc:
                raise AsusMouseError(f"{label}失败：{exc}") from exc
            if not answer:
                continue
            data = bytes(answer)
            if len(data) < 4:
                continue
            # The mouse answers with the report id, the command family and
            # the sub command. An error is answered with FF AA instead.
            if data[1] == 0xFF and data[2] == 0xAA:
                raise AsusMouseError(f"{label}失败：这个固件不支持该命令")
            if data[1] == 0 and data[2] == 0 and data[3] == 0:
                # The mouse is asleep; it acknowledges with an empty report.
                empty = True
                continue
            if (data[0] != self.report_id or data[1] != packet[1]
                    or data[2] != packet[2]):
                # A button/profile event or an answer to an older command.
                continue
            return data

        if empty:
            raise AsusMouseAsleep(f"{label}失败：鼠标没有响应")
        raise AsusMouseError(f"{label}失败：鼠标没有响应")

    def _read(self, *args: int, label: str) -> bytes:
        """Sends a read command and returns the answer."""
        packet = _build_packet(self.report_id, FAMILY_READ, *args,
                               size=self.packet_size)
        answer = self._exchange(packet, label)
        if answer is None:
            raise AsusMouseError(f"{label}失败：鼠标没有响应")
        return answer

    def _write(self, *args: int, label: str) -> None:
        """Sends a write command and saves the settings."""
        packet = _build_packet(self.report_id, FAMILY_WRITE, *args,
                               size=self.packet_size)
        self._exchange(packet, label)
        self.save()

    def save(self) -> None:
        """Persists the settings in the onboard memory.

        Without this command the mouse only echoes the write back and
        forgets it as soon as it is unplugged.
        """
        packet = _build_packet(self.report_id, FAMILY_PROFILE, 0x03,
                               size=self.packet_size)
        self._exchange(packet, "保存设置")

    # ------------------------------------------------------------------
    # Battery
    # ------------------------------------------------------------------

    def get_battery(self) -> tuple[int, bool]:
        """Reads the battery level and the charging state.

        The ASUS mice report the percentage directly, unlike the Razer
        ones which report a raw value.
        """
        answer = self._read(SUB_BATTERY, label="读取电量")
        if (len(answer) < 11 or answer[1] != FAMILY_READ
                or answer[2] != SUB_BATTERY):
            raise AsusMouseError("读取电量失败：回答的不是电量命令")
        return answer[5], answer[10] > 0

    # ------------------------------------------------------------------
    # DPI
    # ------------------------------------------------------------------

    def get_dpi_stages(self) -> list[AsusDpiStage]:
        """Reads the DPI stages.

        The Aimpoint has an independent x and y DPI, so every stage takes
        four bytes: two for x and two for y. Both are little endian, and
        the value is stored in steps of 50 starting at 50.
        """
        answer = self._read(SUB_SETTING, SUB_DPI_XY, label="读取 DPI")
        if (len(answer) < 6 or answer[1] != FAMILY_READ
                or answer[2] != SUB_SETTING):
            raise AsusMouseError("读取 DPI 失败：回答的不是 DPI 命令")
        if answer[3] != SUB_DPI_XY:
            raise AsusMouseError("读取 DPI 失败：回答的不是 X/Y DPI 命令")

        stages: list[AsusDpiStage] = []
        for i in range(DPI_STAGE_COUNT):
            offset = 5 + i * 4
            if offset + 3 >= len(answer):
                break
            x = answer[offset] | (answer[offset + 1] << 8)
            y = answer[offset + 2] | (answer[offset + 3] << 8)
            stages.append(AsusDpiStage(
                dpi_x=x * DPI_INCREMENT + DPI_INCREMENT,
                dpi_y=y * DPI_INCREMENT + DPI_INCREMENT))
        return stages

    def set_dpi_stage(self, stage: int, dpi_x: int, dpi_y: int,
                      red: int = 0, green: int = 0, blue: int = 0) -> None:
        """Writes one DPI stage.

        The stage number starts at 1, and the DPI is stored in steps of
        50 starting at 50. The packet carries the x DPI in two little
        endian bytes, followed by the colour of the stage.
        """
        if stage < 1 or stage > DPI_STAGE_COUNT:
            raise AsusMouseError(
                f"DPI 挡位 {stage} 不在 1-{DPI_STAGE_COUNT} 之间")
        if not (MIN_DPI <= dpi_x <= MAX_DPI):
            raise AsusMouseError(f"DPI {dpi_x} 超出 {MIN_DPI}-{MAX_DPI}")

        encoded = (dpi_x - DPI_INCREMENT) // DPI_INCREMENT
        self._write(SUB_SET, stage - 1, 0x00,
                    encoded & 0xFF, (encoded >> 8) & 0xFF,
                    red, green, blue,
                    label=f"设置第 {stage} 档 DPI")

    # ------------------------------------------------------------------
    # Polling rate
    # ------------------------------------------------------------------

    def get_polling_rate(self) -> int:
        """Reads the polling rate in Hz."""
        answer = self._read(SUB_SETTING, 0x00, label="读取回报率")
        if (len(answer) < 14 or answer[1] != FAMILY_READ
                or answer[2] != SUB_SETTING or answer[3] != 0x00):
            raise AsusMouseError("读取回报率失败：回答的不是回报率命令")
        raw = answer[13] & 0x07
        for rate, code in POLLING_RATES.items():
            if code == raw:
                return rate
        return 0

    def set_polling_rate(self, rate: int) -> None:
        """Writes the polling rate in Hz."""
        if rate not in POLLING_RATES:
            raise AsusMouseError(f"回报率 {rate} Hz 不受支持")
        self._write(SUB_SET, 0x04, 0x00, POLLING_RATES[rate],
                    label=f"设置回报率 {rate} Hz")

    # ------------------------------------------------------------------
    # Button mapping
    # ------------------------------------------------------------------

    def list_buttons(self) -> list[int]:
        """Lists the button ids of the mouse.

        The ASUS mice always have the same buttons, so the list is fixed
        rather than read from the device.
        """
        return list(BUTTON_ORDER)

    def get_button_mapping(self, button_id: int) -> AsusButtonMapping:
        """Reads the action assigned to one button.

        The mouse answers with one two byte action code per slot, in the
        order of :data:`BUTTON_ORDER`. The bytes are little endian.
        """
        answer = self._read(SUB_BUTTONS, 0x00, 0x00, 0x00,
                            label="读取按键映射")
        if (len(answer) < 6 or answer[1] != FAMILY_READ
                or answer[2] != SUB_BUTTONS):
            raise AsusMouseError("读取按键映射失败：回答的不是按键命令")

        slot = BUTTON_ORDER.index(button_id) \
            if button_id in BUTTON_ORDER else None
        if slot is None:
            raise AsusMouseError(f"按键 0x{button_id:04X} 不在映射表里")

        offset = 5 + slot * 2
        if offset + 1 >= len(answer):
            raise AsusMouseError(f"按键 0x{button_id:04X} 不在映射表里")
        action_code = answer[offset] | (answer[offset + 1] << 8)
        return AsusButtonMapping(button_id=button_id,
                                 action_code=action_code)

    def set_button_action(self, button_id: int, action_code: int) -> None:
        """Writes the action of one button.

        The packet carries the source code of the button and the wanted
        action code, both little endian.
        """
        self._write(SUB_SET_BUTTON, 0x00, 0x00,
                    button_id & 0xFF, (button_id >> 8) & 0xFF,
                    action_code & 0xFF, (action_code >> 8) & 0xFF,
                    label=f"设置按键 0x{button_id:04X} 的映射")

    def reset_button(self, button_id: int) -> None:
        """Restores one button to its factory default.

        The factory default is the button's own source code, so the
        firmware falls back to its built-in behaviour for it.
        """
        self.set_button_action(button_id, default_action_code(button_id))

    def assign_button_code(self, button_id: int, code: int) -> None:
        """Makes a button emit the click of another mouse button."""
        self.set_button_action(button_id, code)

    def reset_all_buttons(self) -> None:
        """Restores every button to its factory default."""
        for button_id in BUTTON_ORDER:
            self.reset_button(button_id)

    def reset_to_factory(self) -> None:
        """Restores the whole configuration of the mouse.

        The protocol has no "factory reset" command, so every part of the
        configuration is written back separately: the buttons go to their
        built-in behaviour, the DPI stages are replaced by the default
        ones, and the polling rate goes to its default.
        """
        self.reset_all_buttons()
        for index, dpi in enumerate(DEFAULT_STAGES[:DPI_STAGE_COUNT]):
            self.set_dpi_stage(index + 1, dpi, dpi)
        self.set_polling_rate(DEFAULT_POLLING_RATE)

    # ------------------------------------------------------------------
    # Profiles
    # ------------------------------------------------------------------

    def get_profile(self) -> tuple[int, int]:
        """Reads the active profile and the active DPI stage."""
        answer = self._read(SUB_DEVICE_INFO, label="读取配置文件")
        if (len(answer) < 13 or answer[1] != FAMILY_READ
                or answer[2] != SUB_DEVICE_INFO or answer[3] != 0x00):
            raise AsusMouseError("读取配置文件失败：回答的不是设备信息命令")
        return answer[11], answer[12]

    def set_profile(self, profile: int) -> None:
        """Switches to another onboard profile."""
        if profile < 0 or profile >= PROFILE_COUNT:
            raise AsusMouseError(
                f"配置文件 {profile} 不在 0-{PROFILE_COUNT - 1} 之间")
        packet = _build_packet(self.report_id, FAMILY_PROFILE, 0x02, profile,
                               size=self.packet_size)
        self._exchange(packet, f"切换到配置文件 {profile}")
        self.save()

    # ------------------------------------------------------------------
    # High level helpers
    # ------------------------------------------------------------------

    def get_settings(self) -> AsusMouseSettings:
        """Reads every setting the mouse exposes."""
        settings = AsusMouseSettings()
        try:
            settings.battery, settings.charging = self.get_battery()
        except AsusMouseError:
            pass
        try:
            settings.dpi_stages = self.get_dpi_stages()
        except AsusMouseError:
            pass
        try:
            settings.polling_rate = self.get_polling_rate()
        except AsusMouseError:
            pass
        try:
            settings.active_profile, settings.active_dpi_stage = \
                self.get_profile()
        except AsusMouseError:
            pass
        return settings

    def apply_settings(self, dpi: int | None = None,
                       polling_rate: int | None = None,
                       stages: list[AsusDpiStage] | None = None,
                       active_stage: int = 0) -> AsusMouseSettings:
        """Writes the given settings and reads them back for a check.

        Every write is confirmed by reading the value again, so a mouse
        that silently ignores a command is reported instead of pretending
        the change worked.
        """
        if polling_rate is not None:
            self.set_polling_rate(polling_rate)

        if stages:
            for index, stage in enumerate(stages):
                dpi_x = stage.dpi_x
                dpi_y = stage.dpi_y
                # A plain stage only carries one value, so both axes get
                # the same number.
                if dpi_x and not dpi_y:
                    dpi_y = dpi_x
                if dpi_y and not dpi_x:
                    dpi_x = dpi_y
                self.set_dpi_stage(index + 1, dpi_x, dpi_y,
                                   stage.red, stage.green, stage.blue)
        elif dpi is not None:
            # Without a stage list the DPI goes into the first stage.
            self.set_dpi_stage(1, dpi, dpi)

        settings = self.get_settings()
        if polling_rate is not None and settings.polling_rate != polling_rate:
            raise AsusMouseError(
                f"回报率写入后回读不一致：目标 {polling_rate}，"
                f"实际 {settings.polling_rate}")
        if stages:
            for index, stage in enumerate(stages):
                if index >= len(settings.dpi_stages):
                    break
                actual = settings.dpi_stages[index]
                # The write command carries one DPI value and the mouse
                # applies it to both axes. Only the X value can be
                # verified; the Y bytes are informational.
                if actual.dpi_x != stage.dpi_x:
                    raise AsusMouseError(
                        f"第 {index + 1} 档 DPI 写入后回读不一致："
                        f"目标 {stage.dpi_x}，实际 {actual.dpi_x}")
        return settings

    def close(self) -> None:
        """Releases the HID handle."""
        if self._handle is not None:
            try:
                self._handle.close()
            except Exception:
                pass
            self._handle = None

    def __enter__(self) -> "AsusMouseController":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _path_text(path: bytes | str) -> str:
    """Returns a HID path as lower case text."""
    if isinstance(path, bytes):
        path = path.decode("utf-8", errors="replace")
    return path.lower()


def _is_control_interface(dev: dict) -> bool:
    """Whether an ASUS HID interface is the one that carries commands.

    The direct connection exposes the control collection as ``MI_00``;
    the Omni receiver multiplexes it on ``MI_02&Col03``. Filtering only by
    the vendor usage page is fragile because some ASUS keyboards use a
    vendor page too, so the known mouse product ids are checked first.
    """
    product_id = dev.get("product_id")
    if product_id not in ASUS_DEVICES:
        return False

    path = _path_text(dev.get("path", ""))
    if product_id == PRODUCT_OMNI_RECEIVER:
        if "mi_02&col03" in path:
            return True
    elif "mi_00" in path:
        return True

    # A HID path with a collection belongs to a known mouse, but not to
    # the control channel; do not fall back to the usage page for those.
    if "mi_" in path or "&col" in path:
        return False

    # Older firmware and the wired variants keep the collection on the
    # vendor page; this fallback still finds those.
    return (dev.get("usage_page") == USAGE_PAGE_VENDOR
            and dev.get("usage") == 1)


def _candidate_interfaces() -> list[dict]:
    """Lists the ASUS HID interfaces that can carry the settings."""
    candidates = []
    for dev in hidsupport.enumerate_interfaces(ASUS_VID):
        if dev.get("vendor_id") != ASUS_VID:
            continue
        if not _is_control_interface(dev):
            continue
        candidates.append(dev)

    def rank(dev: dict) -> tuple[int, int, int]:
        path = _path_text(dev.get("path", ""))
        if dev.get("product_id") == PRODUCT_OMNI_RECEIVER:
            preferred = 0 if "mi_02&col03" in path else 1
        else:
            preferred = 0 if "mi_00" in path else 1
        return (preferred, dev.get("interface_number", 0),
                dev.get("product_id", 0))

    candidates.sort(key=rank)
    return candidates


def _report_id_for(product_id: int) -> int:
    """The report id depends on the connection.

    Behind the ROG Omni receiver the packets start with ``0x03``, a
    direct cable connection uses ``0x00``.
    """
    return 0x03 if product_id == PRODUCT_OMNI_RECEIVER else 0x00


def _packet_size_for(product_id: int) -> int:
    """The HID report size of the control interface.

    The direct interface accepts a 64-byte report and carries the report
    id in front of it (65 bytes in total). The Omni receiver's report is
    64 bytes including the id. Both values come from g-helper, which is
    tested against the real devices.
    """
    return OMNI_PACKET_SIZE if product_id == PRODUCT_OMNI_RECEIVER \
        else PACKET_SIZE


def _device_name(product_id: int, product_string: str) -> str:
    """The friendly name of the mouse."""
    known = ASUS_DEVICES.get(product_id)
    if known:
        return known
    return product_string or f"ASUS Device {product_id:04X}"


def _connection_label(product_id: int) -> str:
    """The connection the mouse uses."""
    if product_id == PRODUCT_WIRED:
        return "USB"
    if product_id == PRODUCT_WIRELESS:
        return "2.4G"
    if product_id == PRODUCT_BLUETOOTH:
        return "蓝牙"
    if product_id == PRODUCT_OMNI_RECEIVER:
        return "Omni 接收器"
    return ""


@dataclass(frozen=True)
class AsusDevice:
    """One ASUS mouse that answered."""

    name: str
    percent: int
    charging: bool
    product_id: int
    connection: str
    # The polling rate the mouse is set to, in Hz. Zero when the mouse did
    # not answer the query.
    polling_rate: int = 0
    # The DPI the mouse is set to. Zero when the mouse did not answer.
    dpi: int = 0


def read_devices() -> list[AsusDevice]:
    """Reads the battery level of every connected ASUS mouse.

    The control interface is only available over USB or the 2.4 GHz
    receiver. In Bluetooth mode Windows exposes the mouse as a BLE HID
    device instead, which the HID driver cannot reach; the Bluetooth
    driver reports that connection separately.
    """
    found: list[AsusDevice] = []
    seen: set[tuple[int, str]] = set()

    for dev in _candidate_interfaces():
        product_id = dev["product_id"]
        path = dev["path"]
        if isinstance(path, bytes):
            path = path.decode("utf-8", errors="replace")

        key = (product_id, path)
        if key in seen:
            continue
        seen.add(key)

        try:
            controller = AsusMouseController(
                path, product_id,
                _device_name(product_id, dev.get("product_string") or ""),
                _report_id_for(product_id))
        except AsusMouseError:
            continue

        # One handle is enough for all reads. Opening a second one while
        # the first is still open can fail because the control interface
        # is exclusive on some firmware versions.
        try:
            try:
                percent, charging = controller.get_battery()
            except AsusMouseError:
                continue
            if percent <= 0:
                # A zero reading usually means the mouse is asleep rather
                # than genuinely empty.
                continue

            # The polling rate and the DPI are optional: a mouse that does
            # not answer them is still shown, it just does not report the
            # two values.
            polling_rate = 0
            try:
                polling_rate = controller.get_polling_rate()
            except AsusMouseError:
                pass
            dpi = 0
            try:
                stages = controller.get_dpi_stages()
            except AsusMouseError:
                stages = []
            if stages:
                dpi = stages[0].dpi_x

            found.append(AsusDevice(
                name=controller.name,
                percent=min(100, percent),
                charging=charging,
                product_id=product_id,
                connection=_connection_label(product_id),
                polling_rate=polling_rate,
                dpi=dpi,
            ))
        finally:
            controller.close()

    return found


def open_mouse(product_id: int | None = None) -> AsusMouseController | None:
    """Opens the first ASUS mouse that answers, or returns ``None``.

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
            controller = AsusMouseController(
                path, pid,
                _device_name(pid, dev.get("product_string") or ""),
                _report_id_for(pid))
        except AsusMouseError as exc:
            errors.append(f"PID 0x{pid:04X}: {exc}")
            continue

        try:
            controller.get_battery()
        except AsusMouseAsleep:
            controller.close()
            raise
        except AsusMouseError as exc:
            errors.append(f"PID 0x{pid:04X}: {exc}")
            controller.close()
            continue
        return controller

    if errors:
        raise AsusMouseError("找到鼠标但没有接口响应配置命令：\n"
                             + "\n".join(errors))
    return None
