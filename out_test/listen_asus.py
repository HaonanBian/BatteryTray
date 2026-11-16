"""Listens on every ASUS collection for a pushed battery report.

The Linux driver reads the battery with a GET_REPORT on an input report,
which Windows has no equivalent for. The keyboard may push the report
instead, so this listens on every collection and prints anything that
starts with 0x03.
"""

import time

import hid

ASUS_VID = 0x0B05

for dev in hid.enumerate(ASUS_VID):
    path = dev.get("path", b"")
    try:
        handle = hid.device()
        handle.open_path(path)
    except OSError as exc:
        print(f"open failed: {exc}")
        continue

    print(f"\n== page={dev.get('usage_page')} usage={dev.get('usage')} "
          f"intf={dev.get('interface_number')} ==")

    deadline = time.time() + 3.0
    seen = 0
    while time.time() < deadline and seen < 12:
        try:
            data = handle.read(64, timeout_ms=200)
        except OSError as exc:
            print(f"  read failed: {exc}")
            break
        if data:
            seen += 1
            print(f"  {bytes(data).hex(' ')}")

    try:
        handle.close()
    except Exception:
        pass
