import hid, time
VID, PID = 0x320F, 0x5088
path=[d for d in hid.enumerate(VID,PID) if d.get("usage_page")==0xFF1C][0]["path"]
def frame(cmd, param=0, data=b""):
    b=bytearray(64); b[0]=0x04; b[3]=cmd; b[4]=len(data); b[5]=param; b[8:8+len(data)]=data
    s=sum(b[3:64])&0xFFFF; b[1]=s&0xFF; b[2]=(s>>8)&0xFF; return bytes(b)
h=hid.device(); h.open_path(path)
for cmd in (0x09,0x00,0x08,0x0a,0x0b,0x0c,0x0d,0x0e,0x0f):
    h.write(frame(cmd)); time.sleep(0.1)
    got=[]
    end=time.time()+1.2
    while time.time()<end:
        r=h.read(64,timeout_ms=100)
        if r: got.append(bytes(r)[:16].hex(" "))
    print(hex(cmd),got)
h.close()
