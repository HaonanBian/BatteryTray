"""Looks for the ASUS keyboard battery answer in the g-helper packet shape.

g-helper writes ``reportId 0x12 0x01`` padded to 65 bytes and reads an
answer of the same shape whose byte 6 is the percentage and byte 9 the
charging flag.
"""

import time

import hid

ASUS_VID = 0x0B05
TARGET_PID = 0x19B6


def try_collection(dev, label):
    path = dev.get("path", b"")
    try:
        handle = hid.device()
        handle.open_path(path)
    except OSError as exc:
        print(f"  {label}: open failed {exc}")
        return

    for report_id in (0x00, 0x02, 0x5D):
        packet = bytes([report_id, 0x12, 0x01]) + bytes(62)
        try:
            handle.write(packet)
        except OSError as exc:
            print(f"  {label} rid={report_id:02X}: write failed {exc}")
            continue

        deadline = time.time() + 1.5
        while time.time() < deadline:
            try:
                data = bytes(handle.read(65, timeout_ms=200))
            except OSError:
                break
            if not data:
                continue
            ok = len(data) > 2 and data[1] == 0x12 and data[2] == 0x01
            print(f"  {label} rid={report_id:02X}: {data[:14].hex(' ')}"
                  f"{'   <== battery answer' if ok else ''}")
            if ok:
                print(f"      level={data[6]} charging={data[9] == 1}")

    try:
        handle.close()
    except Exception:
        pass


for dev in hid.enumerate(ASUS_VID):
    if dev["product_id"] != TARGET_PID:
        continue
    page = dev.get("usage_page")
    print(f"\n== page={page:04X} usage={dev.get('usage')} "
          f"intf={dev.get('interface_number')} ==")
    try_collection(dev, f"page={page:04X}/{dev.get('usage')}")
