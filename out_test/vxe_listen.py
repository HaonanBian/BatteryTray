import hid, time
VID, PID = 0x320F, 0x5088
devs=[d for d in hid.enumerate(VID,PID) if d.get("usage_page")==0xFF1C]
h=hid.device(); h.open_path(devs[0]["path"])
h.set_nonblocking(0)
print("product",h.get_product_string())
end=time.time()+3
seen=set()
while time.time()<end:
    try:
        r=h.read(64, timeout_ms=200)
    except Exception as e:
        print("read err",e); break
    if r:
        b=bytes(r)
        if b not in seen:
            seen.add(b)
            print(len(b), b.hex(" "))
print("reports",len(seen))
h.close()
