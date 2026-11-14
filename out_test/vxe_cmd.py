import hid, time
VID, PID = 0x320F, 0x5088
path=[d for d in hid.enumerate(VID,PID) if d.get("usage_page")==0xFF1C][0]["path"]
def frame(cmd, param=0, data=b""):
    b=bytearray(64); b[0]=0x04; b[3]=cmd; b[4]=len(data); b[5]=param; b[8:8+len(data)]=data
    s=sum(b[3:64])&0xFFFF; b[1]=s&0xFF; b[2]=(s>>8)&0xFF; return bytes(b)
h=hid.device(); h.open_path(path)
# wait for periodic status
for i in range(80):
    r=h.read(64,timeout_ms=100)
    if r: print("periodic", bytes(r)[:12].hex(" ")); break
for cmd in (0x00,0x08,0x09,0x03,0x04,0x05,0x06):
    # drain
    while h.read(64,timeout_ms=50): pass
    t=time.time(); h.write(frame(cmd)); time.sleep(0.05)
    got=[]
    while time.time()-t < 1.0:
        r=h.read(64,timeout_ms=100)
        if r: got.append((round(time.time()-t,2),bytes(r)))
    print("cmd",hex(cmd),[(dt,b[:12].hex(" ")) for dt,b in got])
h.close()
