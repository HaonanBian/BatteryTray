"""A shared helper for listing the HID interfaces of the machine.

The ``hid`` package talks to the HID subsystem of Windows through a
native library. On some machines that library is refused, for example
because the process may not open the HID device or because the subsystem
is not available at all. The failure then reaches the caller as an
exception.

A driver that cannot even list the interfaces has nothing to report, but
it must not take the other drivers down with it. Every driver therefore
asks through this helper, which turns the failure into an empty list.
"""

from __future__ import annotations

import hid


def enumerate_interfaces(vendor_id: int | None = None) -> list[dict]:
    """Lists the HID interfaces of the machine.

    Returns an empty list when the HID subsystem cannot be reached. The
    caller then simply finds no device, which is the same outcome as a
    machine that has no HID device attached.
    """
    try:
        if vendor_id is None:
            return list(hid.enumerate())
        return list(hid.enumerate(vendor_id))
    except Exception:
        # The HID subsystem refused to answer. There is nothing to report.
        return []
