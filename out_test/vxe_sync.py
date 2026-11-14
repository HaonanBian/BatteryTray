import hid, time
VID, PID = 0x320F, 0x5088
path=[d for d in hid.enumerate(VID,PID) if d.get("usage_page")==0xFF1C][0]["path"]
def frame(cmd, param=0, data=b""):
    b=bytearray(64); b[0]=0x04; b[3]=cmd; b[4]=len(data); b[5]=param; b[8:8+len(data)]=data
    s=sum(b[3:64])&0xFFFF; b[1]=s&0xFF; b[2]=(s>>8)&0xFF; return bytes(b)
h=hid.device(); h.open_path(path)
for trial in range(3):
    # wait for a status report
    while True:
        r=h.read(64,timeout_ms=100)
        if r and bytes(r)[1]==0:
            print("synced", bytes(r)[:10].hex(" ")); break
    # drain anything else
    while h.read(64,timeout_ms=20): pass
    t=time.time(); h.write(frame(0x09 if trial%2==0 else 0x00))
    got=None
    while time.time()-t<2.0:
        r=h.read(64,timeout_ms=100)
        if r and bytes(r)[1]==0:
            got=(round(time.time()-t,2),bytes(r)); break
    print("trial",trial,"cmd",hex(0x09 if trial%2==0 else 0x00),"->",got[0] if got else None, got[1][:10].hex(" ") if got else "")
h.close()
