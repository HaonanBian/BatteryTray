import hid, time
VID, PID = 0x320F, 0x5088
path=[d for d in hid.enumerate(VID,PID) if d.get("usage_page")==0xFF1C][0]["path"]
req=bytearray(64); req[0]=0x04; req[3]=0x1A; req[4]=0x06
h=hid.device(); h.open_path(path)
for attempt in range(3):
    while h.read(64,timeout_ms=10): pass
    h.write(bytes(req)); time.sleep(0.3)
    end=time.time()+1.5
    while time.time()<end:
        r=h.read(64,timeout_ms=150)
        if r:
            b=bytes(r)
            print("reply",b[:16].hex(" "))
            if len(b)>=10 and b[0]==0x04 and b[3]==0x1A:
                print("percent",b[8],"charging",b[9])
    time.sleep(0.3)
h.close()
