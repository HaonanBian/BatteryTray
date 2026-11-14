import hid, time
VID, PID = 0x320F, 0x5088
devs = [d for d in hid.enumerate(VID, PID) if d.get("usage_page") == 0xFF1C]
print("devs", len(devs))
for d in devs:
    print(d.get("path"), d.get("usage_page"), d.get("usage"), d.get("interface_number"))
    h = hid.device(); h.open_path(d["path"])
    print("product", h.get_product_string(), "mfg", h.get_manufacturer_string())
    for rid in range(0, 33):
        try:
            data = bytes(h.get_feature_report(rid, 65))
            if any(data):
                print("F", rid, len(data), data[:24].hex(" "))
        except Exception as e:
            pass
    h.close()
