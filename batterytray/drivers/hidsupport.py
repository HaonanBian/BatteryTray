"""A shared helper for listing the HID interfaces of the machine.

The ``hid`` package talks to the HID subsystem of Windows through a
native library. On some machines that library is refused, for example
because the process may not open the HID device or because the subsystem
is not available at all. The failure then reaches the caller as an
exception.

A driver that cannot even list the interfaces has nothing to report, but
it must not take the other drivers down with it. Every driver therefore
asks through this helper, which turns the failure into an empty list.

The failure is remembered as well. A driver that quietly gets nothing back
looks exactly like a machine that has no HID device attached, so the reason
would be lost. The counter lets the app report it.
"""

from __future__ import annotations

import hid


# How many times the HID subsystem refused to answer since the app started.
_failure_count = 0
_last_error = ""


def enumerate_interfaces(vendor_id: int | None = None) -> list[dict]:
    """Lists the HID interfaces of the machine.

    Returns an empty list when the HID subsystem cannot be reached. The
    caller then simply finds no device, which is the same outcome as a
    machine that has no HID device attached.
    """
    global _failure_count, _last_error
    try:
        if vendor_id is None:
            return list(hid.enumerate())
        return list(hid.enumerate(vendor_id))
    except Exception as error:
        # The HID subsystem refused to answer. There is nothing to report,
        # but the reason is kept so that the app can tell it to the user.
        _failure_count += 1
        _last_error = str(error) or type(error).__name__
        return []


def failure_count() -> int:
    """How often the HID subsystem refused to answer."""
    return _failure_count


def last_error() -> str:
    """The reason the HID subsystem gave the last time it refused."""
    return _last_error
