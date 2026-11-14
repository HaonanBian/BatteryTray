import hid, time
VID, PID = 0x320F, 0x5088
path=[d for d in hid.enumerate(VID,PID) if d.get("usage_page")==0xFF1C][0]["path"]
h=hid.device(); h.open_path(path)
start=time.time(); last=None
while time.time()-start < 15:
    r=h.read(64,timeout_ms=300)
    if r:
        b=bytes(r)
        if b!=last:
            print(f"{time.time()-start:5.1f}s", b[:20].hex(" "))
            last=b
h.close()
