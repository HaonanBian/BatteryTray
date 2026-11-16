"""Finds the ASUS keyboard control collection and its battery answer.

g-helper probes a candidate collection with the version query
``reportId 0x12 0x00`` and expects the answer to echo ``12 00``. The
same family answers the power query ``reportId 0x12 0x01``, whose byte 6
is the percentage and byte 9 the charging flag.
"""

import time

import hid

ASUS_VID = 0x0B05


def drain(handle, size=65, timeout_ms=50):
    while True:
        try:
            data = handle.read(size, timeout_ms=timeout_ms)
        except OSError:
            return
        if not data:
            return


def main():
    for dev in hid.enumerate(ASUS_VID):
        path = dev.get("path", b"")
        page = dev.get("usage_page")
        usage = dev.get("usage")
        try:
            handle = hid.device()
            handle.open_path(path)
        except OSError as exc:
            print(f"page={page:04X} usage={usage}: open failed {exc}")
            continue

        print(f"\n== page={page:04X} usage={usage} ==")
        for report_id in (0x00, 0x02, 0x03):
            for sub in (0x00, 0x01):
                packet = bytes([report_id, 0x12, sub]) + bytes(62)
                try:
                    drain(handle)
                    handle.write(packet)
                except OSError as exc:
                    print(f"  rid={report_id:02X} sub={sub:02X}: write failed {exc}")
                    continue

                deadline = time.time() + 0.6
                while time.time() < deadline:
                    try:
                        data = bytes(handle.read(65, timeout_ms=150))
                    except OSError:
                        break
                    if not data:
                        continue
                    head = data[:12].hex(" ")
                    tag = ""
                    if len(data) > 2 and data[1] == 0x12:
                        tag = "  <== echoes 12"
                        if data[2] == sub:
                            tag += f" (sub {sub:02X})"
                            if sub == 0x01:
                                tag += (f"  level={data[6]}"
                                        f" charging={data[9] == 1}")
                    print(f"  rid={report_id:02X} sub={sub:02X}: {head}{tag}")

        try:
            handle.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
