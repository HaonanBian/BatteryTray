import hid
VID, PID = 0x320F, 0x5088
for d in hid.enumerate(VID, PID):
    h = hid.device(); h.open_path(d["path"])
    try:
        desc = bytes(h.get_report_descriptor())
        print("IF", d.get("interface_number"), "usage", hex(d.get("usage_page",0)), hex(d.get("usage",0)), "desc_len", len(desc))
        print(desc.hex(" "))
    except Exception as e:
        print("err", e)
    finally:
        h.close()
