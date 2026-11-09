"""Battery driver for Bluetooth and generic HID devices.

Windows exposes a device's Bluetooth battery level through an undocumented PnP
property, ``DEVPKEY_Bluetooth_BatteryLevel``
(``{104EA319-6EE2-4701-BD47-8DDBF425BBE5}``, property id 2), stored as a
``DEVPROP_TYPE_BYTE`` percentage.

The property is written by the Bluetooth stack when the peripheral reports its
level over HFP, so it only exists on the *Hands-Free* (or A2DP) node of the
device, not on its main node. Reading it from the main node is the usual reason
"my headset shows no battery" tutorials fail.

The value is *sticky*: Windows keeps the last reported level on the device node
and never clears it when the peripheral is switched off or goes out of range.
Reporting it blindly makes a disconnected headset look like a full battery
forever, so the driver also reads the connection state and only reports a
level for devices that are actually reachable.

References:
    fastfetch-cli/fastfetch                  - src/detection/bluetooth/bluetooth_windows.c
    yszyszysz233/2.4G-battery-viewer        - bt_battery.py
    intellinside/battery-status              - C# device providers
    nikvoronin/Xm4Battery                    - device property reference
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import datetime
from dataclasses import dataclass

setupapi = ctypes.WinDLL("setupapi", use_last_error=True)


class GUID(ctypes.Structure):
    """Windows ``GUID``/``UUID`` structure.

    ``ctypes.wintypes`` does not ship a GUID type on every Python build, so it
    is defined here.
    """

    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", wt.DWORD)]


class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("ClassGuid", GUID),
        ("DevInst", wt.DWORD),
        ("Reserved", ctypes.POINTER(ctypes.c_ulong)),
    ]


# DEVPKEY_Bluetooth_BatteryLevel
FMTID_BLUETOOTH = GUID(
    0x104EA319, 0x6EE2, 0x4701,
    (ctypes.c_ubyte * 8)(0xBD, 0x47, 0x8D, 0xDB, 0xF4, 0x25, 0xBB, 0xE5),
)
PID_BATTERY_LEVEL = 2

# The moment the peripheral last reported its battery level. Windows refreshes
# it every time the device sends a battery report over HFP or GATT, so a
# recent value proves the device was reachable at that moment.
PID_BATTERY_REPORTED = 7

# The device enumeration property set. Property id 15 is the "is connected"
# flag the Bluetooth stack maintains for every paired node.
FMTID_DEVICE_ENUM = GUID(
    0x83DA6326, 0x97A6, 0x4088,
    (ctypes.c_ubyte * 8)(0x94, 0x53, 0xA1, 0x92, 0x3F, 0x57, 0x3B, 0x29),
)
PID_IS_CONNECTED = 15

# DEVPKEY_Bluetooth_* lives in its own property set.
FMTID_BLUETOOTH_INFO = GUID(
    0x2BD67D8B, 0x8BEB, 0x48D5,
    (ctypes.c_ubyte * 8)(0x87, 0xE0, 0x6C, 0xDA, 0x34, 0x28, 0x04, 0x0A),
)
# The Bluetooth address of the device, used to tell nodes of one device apart.
PID_DEVICE_ADDRESS = 1
# The moment the device was last seen.
PID_LAST_CONNECTED = 11

# The Bluetooth stack keeps the class of device of every paired peripheral in
# the registry. The friendly name of a device rarely says what it is, so the
# class of device is the authoritative source.
BTHPORT_DEVICES_KEY = (
    r"SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices")

# The LE appearance value of a HID device. Its low six bits hold the HID
# subcategory, which is what tells a mouse from a keyboard or a gamepad.
HID_SUB_GENERIC = 0x00
HID_SUB_KEYBOARD = 0x01
HID_SUB_MOUSE = 0x02
HID_SUB_JOYSTICK = 0x03
HID_SUB_GAMEPAD = 0x04

# The major class of a class of device value.
COD_MAJOR_AUDIO_VIDEO = 0x04
COD_MAJOR_PERIPHERAL = 0x05

# The minor class of a peripheral.
COD_MINOR_KEYBOARD = 0x01
COD_MINOR_POINTING = 0x02
COD_MINOR_COMBO = 0x03
COD_MINOR_TRACKBALL = 0x04
COD_MINOR_MOUSE = 0x05
COD_MINOR_JOYSTICK = 0x06
COD_MINOR_GAMEPAD = 0x09
COD_MINOR_GAME_CONTROLLER = 0x01

# How long a device may stay silent before it is considered gone. The
# Bluetooth stack refreshes the "last seen" stamp whenever it hears from the
# peripheral, so a device that has not been heard from for a while is off.
DEVICE_SEEN_TIMEOUT_SECONDS = 300

# Windows time stamps count 100-nanosecond ticks since 1601-01-01 UTC.
_FILETIME_EPOCH = datetime.datetime(1601, 1, 1)

DIGCF_ALLCLASSES = 0x04
DIGCF_PRESENT = 0x02
SPDRP_FRIENDLYNAME = 0x0C
# The property store uses its own type tags, which differ from the
# ``DEVPROP_TYPE_*`` constants in the SDK headers.
DEVPROP_TYPE_BYTE = 0x03
DEVPROP_TYPE_FILETIME = 0x10
DEVPROP_TYPE_BOOLEAN = 0x11
DEVPROP_TYPE_STRING = 0x12

setupapi.SetupDiGetClassDevsW.restype = wt.HANDLE
setupapi.SetupDiGetClassDevsW.argtypes = [
    ctypes.c_void_p, ctypes.c_wchar_p, wt.HWND, wt.DWORD]
setupapi.SetupDiEnumDeviceInfo.argtypes = [
    wt.HANDLE, wt.DWORD, ctypes.POINTER(SP_DEVINFO_DATA)]
setupapi.SetupDiGetDevicePropertyW.argtypes = [
    wt.HANDLE, ctypes.POINTER(SP_DEVINFO_DATA), ctypes.POINTER(PROPERTYKEY),
    ctypes.POINTER(wt.DWORD), ctypes.c_void_p, wt.DWORD,
    ctypes.POINTER(wt.DWORD), wt.DWORD]
setupapi.SetupDiGetDeviceRegistryPropertyW.argtypes = [
    wt.HANDLE, ctypes.POINTER(SP_DEVINFO_DATA), wt.DWORD, ctypes.POINTER(wt.DWORD),
    ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD)]
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wt.HANDLE]


@dataclass(frozen=True)
class BluetoothDevice:
    """A device that reported a battery level through the Bluetooth stack."""

    name: str
    address: str
    percent: int
    kind: str
    # ``True`` when the peripheral is currently reachable. Windows keeps the
    # last battery level on the device node, so a disconnected device would
    # otherwise keep showing its final reading forever.
    connected: bool = True
    # When the peripheral last reported its battery level, if Windows recorded
    # it.
    last_report: datetime.datetime | None = None
    # When the peripheral was last seen, if Windows recorded it.
    last_seen: datetime.datetime | None = None


def _friendly_name(dev_info: wt.HANDLE, info: SP_DEVINFO_DATA) -> str:
    """Reads ``SPDRP_FRIENDLYNAME`` for a device node."""
    needed = wt.DWORD(0)
    setupapi.SetupDiGetDeviceRegistryPropertyW(
        dev_info, ctypes.byref(info), SPDRP_FRIENDLYNAME, None, None, 0,
        ctypes.byref(needed))
    if needed.value == 0:
        return ""
    buf = ctypes.create_unicode_buffer(needed.value // 2 + 1)
    setupapi.SetupDiGetDeviceRegistryPropertyW(
        dev_info, ctypes.byref(info), SPDRP_FRIENDLYNAME, None, buf,
        needed.value, ctypes.byref(needed))
    return buf.value


def _read_byte_property(dev_info: wt.HANDLE, info: SP_DEVINFO_DATA,
                        pid: int) -> int | None:
    """Reads a single-byte property, or ``None`` when it is absent."""
    key = PROPERTYKEY(FMTID_BLUETOOTH, pid)
    prop_type = wt.DWORD(0)
    value = ctypes.c_ubyte(0)
    size = wt.DWORD(ctypes.sizeof(value))
    ok = setupapi.SetupDiGetDevicePropertyW(
        dev_info, ctypes.byref(info), ctypes.byref(key), ctypes.byref(prop_type),
        ctypes.byref(value), 1, ctypes.byref(size), 0)
    if not ok or prop_type.value != DEVPROP_TYPE_BYTE:
        return None
    return int(value.value)


def _read_boolean_property(dev_info: wt.HANDLE, info: SP_DEVINFO_DATA,
                           fmtid: GUID, pid: int) -> bool | None:
    """Reads a boolean property, or ``None`` when it is absent.

    The property store keeps booleans in a registry blob whose type tag is
    ``DEVPROP_TYPE_BOOLEAN`` (0x11), so the value byte is read directly.
    """
    key = PROPERTYKEY(fmtid, pid)
    prop_type = wt.DWORD(0)
    value = ctypes.c_ubyte(0)
    size = wt.DWORD(ctypes.sizeof(value))
    ok = setupapi.SetupDiGetDevicePropertyW(
        dev_info, ctypes.byref(info), ctypes.byref(key), ctypes.byref(prop_type),
        ctypes.byref(value), 1, ctypes.byref(size), 0)
    if not ok or prop_type.value != DEVPROP_TYPE_BOOLEAN:
        return None
    return bool(value.value)


def _read_filetime_property(dev_info: wt.HANDLE, info: SP_DEVINFO_DATA,
                            fmtid: GUID, pid: int) -> datetime.datetime | None:
    """Reads a file time property, or ``None`` when it is absent.

    The value is returned in UTC, which is how the Windows time stamps are
    defined.
    """
    key = PROPERTYKEY(fmtid, pid)
    prop_type = wt.DWORD(0)
    value = ctypes.c_ulonglong(0)
    size = wt.DWORD(ctypes.sizeof(value))
    ok = setupapi.SetupDiGetDevicePropertyW(
        dev_info, ctypes.byref(info), ctypes.byref(key), ctypes.byref(prop_type),
        ctypes.byref(value), ctypes.sizeof(value), ctypes.byref(size), 0)
    if not ok or prop_type.value != DEVPROP_TYPE_FILETIME:
        return None
    stamp = value.value
    if stamp == 0:
        return None
    try:
        return _FILETIME_EPOCH + datetime.timedelta(microseconds=stamp // 10)
    except OverflowError:
        # A corrupt stamp can point far past the last date Python can hold.
        return None


def _read_address(dev_info: wt.HANDLE, info: SP_DEVINFO_DATA) -> str:
    """Reads the Bluetooth device address as ``AA:BB:CC:DD:EE:FF``."""
    key = PROPERTYKEY(FMTID_BLUETOOTH_INFO, PID_DEVICE_ADDRESS)
    prop_type = wt.DWORD(0)
    buf = ctypes.create_unicode_buffer(64)
    size = wt.DWORD(ctypes.sizeof(buf))
    ok = setupapi.SetupDiGetDevicePropertyW(
        dev_info, ctypes.byref(info), ctypes.byref(key), ctypes.byref(prop_type),
        buf, ctypes.sizeof(buf), ctypes.byref(size), 0)
    if not ok or prop_type.value != DEVPROP_TYPE_STRING:
        return ""
    raw = buf.value
    # The stack returns "0xAABBCCDDEEFF" or "AA:BB:CC:DD:EE:FF".
    digits = raw.replace("0x", "").replace(":", "").replace("-", "").replace(" ", "")
    if len(digits) != 12:
        return raw
    return ":".join(digits[i:i + 2] for i in range(0, 12, 2)).upper()


def _classify(name: str, kind_hint: str | None = None) -> str:
    """Guesses what kind of peripheral a node belongs to.

    The name is only a hint: a mouse can be called "ROG KERIS WIRELESS
    AIMPOINT" and a gamepad "Xbox Wireless Controller", so the class of
    device reported by the Bluetooth stack wins whenever it is available.
    """
    if kind_hint:
        return kind_hint

    lowered = name.lower()
    if "hands-free" in lowered or "hands free" in lowered:
        return "headset"
    if "a2dp" in lowered or "audio" in lowered:
        return "headset"
    if "controller" in lowered or "gamepad" in lowered:
        return "controller"
    if "mouse" in lowered or "trackball" in lowered:
        return "mouse"
    if "keyboard" in lowered:
        return "keyboard"
    return "device"


def _read_registry_devices() -> dict[str, dict[str, object]]:
    """Reads the registry record of every paired Bluetooth device.

    The Bluetooth stack keeps the class of device and the moment the device
    was last seen under its address. The friendly name of a device rarely
    says what it is, and the PnP property store does not say whether the
    device is still around, so this is where both facts come from.
    """
    import winreg

    devices: dict[str, dict[str, object]] = {}
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, BTHPORT_DEVICES_KEY)
    except OSError:
        return devices

    try:
        count = winreg.QueryInfoKey(key)[0]
        for index in range(count):
            address = winreg.EnumKey(key, index).upper()
            try:
                device_key = winreg.OpenKey(key, address)
            except OSError:
                continue

            values: dict[str, object] = {}
            try:
                value_count = winreg.QueryInfoKey(device_key)[1]
                for value_index in range(value_count):
                    try:
                        name, value, _type = winreg.EnumValue(device_key, value_index)
                    except OSError:
                        continue
                    values[name] = value
            finally:
                device_key.Close()

            devices[address] = values
    finally:
        key.Close()

    return devices


def _kind_from_class_of_device(values: dict[str, object]) -> str:
    """Derives the kind of a device from its class of device values."""
    # A HID device reports its type in the LE appearance.
    appearance = values.get("LEAppearance")
    if isinstance(appearance, int):
        subcategory = appearance & 0x3F
        if subcategory == HID_SUB_MOUSE:
            return "mouse"
        if subcategory == HID_SUB_KEYBOARD:
            return "keyboard"
        if subcategory in (HID_SUB_JOYSTICK, HID_SUB_GAMEPAD):
            return "controller"

    # A classic device reports it in the class of device. The major class
    # takes the lowest five bits and the minor class the three bits above it.
    cod = values.get("COD")
    if isinstance(cod, int) and cod:
        major = cod & 0x1F
        minor = (cod >> 5) & 0x07
        if major == COD_MAJOR_AUDIO_VIDEO:
            return "headset"
        if major == COD_MAJOR_PERIPHERAL:
            if minor == COD_MINOR_KEYBOARD:
                return "keyboard"
            if minor in (COD_MINOR_POINTING, COD_MINOR_TRACKBALL,
                         COD_MINOR_MOUSE, COD_MINOR_COMBO):
                return "mouse"
            if minor in (COD_MINOR_JOYSTICK, COD_MINOR_GAMEPAD,
                         COD_MINOR_GAME_CONTROLLER):
                return "controller"

    return ""


def _registry_last_seen(values: dict[str, object]) -> datetime.datetime | None:
    """The moment the Bluetooth stack last heard from the device.

    The stamp is stored in local time, so it is converted to UTC before it is
    compared with anything else.
    """
    stamp = values.get("LastSeen")
    if not isinstance(stamp, int) or stamp == 0:
        return None
    try:
        local = _FILETIME_EPOCH + datetime.timedelta(microseconds=stamp // 10)
    except OverflowError:
        return None
    # The registry stores local time, so it is turned into UTC.
    return local.astimezone().astimezone(datetime.UTC).replace(tzinfo=None)


def is_headset_like(name: str, kind: str) -> bool:
    """Keeps out controllers and other devices that are not headsets."""
    if kind == "headset":
        return True
    lowered = name.lower()
    if any(word in lowered for word in
           ("hands-free", "hands free", "a2dp", "headset", "headphone", "earphone")):
        return True
    return any(word in lowered for word in ("headset", "headphone", "earphone", "buds"))


def read_devices() -> list[BluetoothDevice]:
    """Reads battery levels of Bluetooth devices known to Windows.

    Each peripheral can expose several nodes (main, Hands-Free, A2DP). They all
    carry the same battery property, so results are de-duplicated by Bluetooth
    address.

    Windows keeps the last reported battery level on the device node after the
    peripheral is switched off, so the connection state is read as well. A
    device is only reported as connected when Windows says so, or when it
    reported its battery level recently enough to prove it is reachable.
    """
    dev_info = setupapi.SetupDiGetClassDevsW(
        None, None, None, DIGCF_ALLCLASSES | DIGCF_PRESENT)
    invalid = ctypes.c_void_p(-1).value
    if not dev_info or dev_info == invalid:
        return []

    # Windows time stamps are UTC, so the comparison uses UTC as well.
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    # The class of device tells what a peripheral really is, and the moment it
    # was last heard from tells whether it is still around. The friendly name
    # often does not say either.
    registry = _read_registry_devices()
    found: dict[str, BluetoothDevice] = {}
    try:
        index = 0
        while True:
            info = SP_DEVINFO_DATA()
            info.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)
            if not setupapi.SetupDiEnumDeviceInfo(dev_info, index, ctypes.byref(info)):
                break
            index += 1

            name = _friendly_name(dev_info, info)
            if not name:
                continue

            level = _read_byte_property(dev_info, info, PID_BATTERY_LEVEL)
            if level is None:
                continue
            if level <= 0:
                # The property exists but the device is not reporting a level.
                continue

            address = _read_address(dev_info, info)
            key = address or name
            if key in found:
                continue

            plain = _plain_address(address)
            record = registry.get(plain, {})

            connected = _read_boolean_property(
                dev_info, info, FMTID_DEVICE_ENUM, PID_IS_CONNECTED)
            last_report = _read_filetime_property(
                dev_info, info, FMTID_BLUETOOTH, PID_BATTERY_REPORTED)
            last_seen = _read_filetime_property(
                dev_info, info, FMTID_BLUETOOTH_INFO, PID_LAST_CONNECTED)
            registry_seen = _registry_last_seen(record)

            found[key] = BluetoothDevice(
                name=name, address=address, percent=min(100, level),
                kind=_classify(name, _kind_from_class_of_device(record)),
                connected=_is_reachable(connected, registry_seen, now),
                last_report=last_report,
                last_seen=last_seen)
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(dev_info)

    return sorted(found.values(), key=lambda d: d.name)


def _plain_address(address: str) -> str:
    """Strips the separators from a Bluetooth address.

    The registry stores the address as plain hex digits, while the PnP
    property uses the usual colon separated form.
    """
    return address.replace(":", "").replace("-", "").replace("0x", "").upper()


def _is_reachable(connected: bool | None, last_seen: datetime.datetime | None,
                  now: datetime.datetime) -> bool:
    """Decides whether a device is really reachable right now.

    The PnP connection flag is authoritative when it says the device is
    connected. When it says the device is gone, the moment the Bluetooth
    stack last heard from it decides: a device that was seen recently is
    still around, one that has been silent for a while is off.

    The battery report time cannot be used for this. Windows rewrites the
    battery property the moment a device disconnects, so a device that just
    switched off would still look like it had just reported its level.
    """
    if connected is True:
        return True
    if last_seen is None:
        # Without any proof, fall back to the flag. A node that publishes no
        # flag at all is assumed to be connected, so a live reading is never
        # hidden.
        return bool(connected)
    age = (now - last_seen).total_seconds()
    return age <= DEVICE_SEEN_TIMEOUT_SECONDS

def read_headsets() -> list[BluetoothDevice]:
    """Returns only the headset-like devices."""
    return [d for d in read_devices() if is_headset_like(d.name, d.kind)]
