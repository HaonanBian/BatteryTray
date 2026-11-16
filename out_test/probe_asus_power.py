"""Probes the ASUS keyboard with the g-helper battery command.

g-helper writes ``reportId 0x12 0x01`` on the vendor collection and reads
the answer: byte 6 is the percentage and byte 9 the charging flag.
"""

import time

import hid

ASUS_VID = 0x0B05

for dev in hid.enumerate(ASUS_VID):
    path = dev.get("path", b"")
    page = dev.get("usage_page")
    if page == 1:
        # The ordinary keyboard and mouse collections cannot be written.
        continue
    try:
        handle = hid.device()
        handle.open_path(path)
    except OSError as exc:
        print(f"open failed: {exc}")
        continue

    print(f"\n== page={page:04X} usage={dev.get('usage')} "
          f"intf={dev.get('interface_number')} ==")

    for report_id in (0x00, 0x02, 0x05):
        for command in (0x01, 0x07):
            request = bytes([report_id, 0x12, command]) + bytes(61)
            try:
                handle.write(request)
            except OSError as exc:
                print(f"  rid={report_id:02X} cmd={command:02X}: write failed {exc}")
                continue

            time.sleep(0.15)
            try:
                answer = bytes(handle.read(64, timeout_ms=300))
            except OSError as exc:
                print(f"  rid={report_id:02X} cmd={command:02X}: read failed {exc}")
                continue
            if answer:
                print(f"  rid={report_id:02X} cmd={command:02X}: {answer.hex(' ')}")

    try:
        handle.close()
    except Exception:
        pass
