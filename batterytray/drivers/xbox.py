"""Battery levels of the Xbox controllers that XInput knows about.

Windows exposes every Xbox controller as an XInput device, whether it is
plugged into a USB port or connected over a wireless adapter. XInput is
the only source that answers for such a controller, because a controller
that is reached over a cable has no Bluetooth node that could carry a
battery level.

The battery state is one of the few things XInput reports about a
controller. It knows four kinds of controller and several states, and the
state that says "unknown" is reported for a controller that is powered
from a cable, because such a controller has no battery at all.

A controller that is connected over Bluetooth is not an XInput device on
Windows, so the Bluetooth driver reports those.

References:
    Microsoft documentation - XInputGetBatteryInformation
    Microsoft documentation - XInputGetState
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
from dataclasses import dataclass

# The number of players XInput knows about.
MAX_USERS = 4

# The kinds of battery a controller can have.
BATTERY_TYPE_UNKNOWN = 0x00
BATTERY_TYPE_DISCONNECTED = 0x01
BATTERY_TYPE_WIRELESS = 0x02

# The states of the battery.
BATTERY_STATE_CHARGING = 0x01
BATTERY_STATE_DISCHARGING = 0x02
BATTERY_STATE_FULL = 0x04
BATTERY_STATE_NOT_CHARGING = 0x08
BATTERY_STATE_UNKNOWN = 0xFF

# The error that XInput answers with when nothing is plugged in.
ERROR_SUCCESS = 0
ERROR_DEVICE_NOT_CONNECTED = 1167


class XINPUT_GAMEPAD(ctypes.Structure):
    """The state of the buttons and the sticks of a gamepad."""

    _fields_ = [
        ("wButtons", wt.WORD),
        ("bLeftTrigger", ctypes.c_ubyte),
        ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX", wt.SHORT),
        ("sThumbLY", wt.SHORT),
        ("sThumbRX", wt.SHORT),
        ("sThumbRY", wt.SHORT),
    ]


class XINPUT_STATE(ctypes.Structure):
    """The full state of a controller."""

    _fields_ = [
        ("dwPacketNumber", wt.DWORD),
        ("Gamepad", XINPUT_GAMEPAD),
    ]


class XINPUT_BATTERY_INFORMATION(ctypes.Structure):
    """The battery of a controller."""

    _fields_ = [
        ("BatteryType", ctypes.c_ubyte),
        ("BatteryState", ctypes.c_ubyte),
    ]


@dataclass(frozen=True)
class XboxDevice:
    """One controller that XInput knows about."""

    name: str
    percent: int | None
    charging: bool
    connected: bool
    wireless: bool


def _load_xinput() -> ctypes.WinDLL | None:
    """Loads the XInput library.

    Several versions exist. The newest one is tried first, because it
    knows the newest controllers.
    """
    for name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
        try:
            return ctypes.WinDLL(name)
        except OSError:
            continue
    return None


def _battery_percent(state: int) -> int | None:
    """Turns a battery state into a percentage.

    XInput does not tell how full the battery is. It only tells whether
    the controller is charging, full, or discharging. A controller that
    is discharging is reported with a rough level, because the real one
    is not known.
    """
    if state == BATTERY_STATE_FULL:
        return 100
    if state == BATTERY_STATE_CHARGING:
        return 100
    if state == BATTERY_STATE_DISCHARGING:
        # The level is not known. A controller that runs on its battery
        # is shown with a level that is worth a look.
        return 50
    return None


def read_devices() -> list[XboxDevice]:
    """Reads the battery of every controller that XInput knows about.

    A controller that is plugged into a cable has no battery, so it is
    reported with an unknown level instead of a made up one.
    """
    dll = _load_xinput()
    if dll is None:
        return []

    dll.XInputGetBatteryInformation.argtypes = [
        ctypes.c_ubyte, ctypes.c_ulong, ctypes.POINTER(XINPUT_BATTERY_INFORMATION)]
    dll.XInputGetBatteryInformation.restype = wt.DWORD
    dll.XInputGetState.argtypes = [
        ctypes.c_ulong, ctypes.POINTER(XINPUT_STATE)]
    dll.XInputGetState.restype = wt.DWORD

    found: list[XboxDevice] = []
    for user in range(MAX_USERS):
        state = XINPUT_STATE()
        # The state is asked for first, because it says whether there is
        # a controller at all.
        if dll.XInputGetState(user, ctypes.byref(state)) != ERROR_SUCCESS:
            continue

        battery = XINPUT_BATTERY_INFORMATION()
        result = dll.XInputGetBatteryInformation(user, 0,
                                                 ctypes.byref(battery))
        if result != ERROR_SUCCESS:
            # The controller is there but does not report a battery,
            # which is what a controller on a cable does.
            found.append(XboxDevice(
                name=f"Xbox 手柄 {user + 1}",
                percent=None,
                charging=False,
                connected=True,
                wireless=False,
            ))
            continue

        charging = battery.BatteryState == BATTERY_STATE_CHARGING
        percent = _battery_percent(battery.BatteryState)
        wireless = battery.BatteryType == BATTERY_TYPE_WIRELESS
        found.append(XboxDevice(
            name=f"Xbox 手柄 {user + 1}",
            percent=percent,
            charging=charging,
            connected=True,
            wireless=wireless,
        ))
    return found
