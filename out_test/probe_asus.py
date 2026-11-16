"""Probes the ASUS ROG keyboard on this machine for its battery report.

The Linux driver (hid-asus.c) reads a 9 byte input report with the report id
0x03: byte 1 is the level (0..255) and byte 8 the charging state. The
question is which HID collection carries that report.
"""

import time

import hid

ASUS_VID = 0x0B05

for dev in hid.enumerate(ASUS_VID):
    print(f"vid={dev['vendor_id']:04X} pid={dev['product_id']:04X} "
          f"page={dev.get('usage_page')} usage={dev.get('usage')} "
          f"intf={dev.get('interface_number')} name={dev.get('product_string')!r}")

print()
print("--- reading every collection for a 0x03 report ---")

for dev in hid.enumerate(ASUS_VID):
    path = dev.get("path", b"")
    try:
        handle = hid.device()
        handle.open_path(path)
    except OSError as exc:
        print(f"  open failed: {exc}")
        continue

    print(f"\n== page={dev.get('usage_page')} usage={dev.get('usage')} "
          f"intf={dev.get('interface_number')} ==")

    # Try a feature report of id 0x03 with the length the driver uses.
    for length in (9, 10, 64):
        try:
            handle.send_feature_report(bytes([0x03]) + bytes(length - 1))
            time.sleep(0.05)
            answer = bytes(handle.get_feature_report(0x03, length))
            print(f"  feature id=3 len={length}: {answer.hex(' ')}")
        except OSError as exc:
            print(f"  feature id=3 len={length}: failed {exc}")

    # Try an output report of id 0x03.
    for length in (9, 10, 64):
        try:
            handle.write(bytes([0x03]) + bytes(length - 1))
            time.sleep(0.05)
            answer = bytes(handle.read(64, timeout_ms=200))
            if answer:
                print(f"  output  id=3 len={length}: {answer.hex(' ')}")
        except OSError as exc:
            print(f"  output  id=3 len={length}: failed {exc}")

    try:
        handle.close()
    except Exception:
        pass
