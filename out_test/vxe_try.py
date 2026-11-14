import hid, time
VID, PID = 0x320F, 0x5088
devs=[d for d in hid.enumerate(VID,PID) if d.get("usage_page")==0xFF1C]
path=devs[0]["path"]

def checksum(buf):
    s=sum(buf[3:64]) & 0xFFFF
    buf[1]=s & 0xFF
    buf[2]=(s>>8)&0xFF

for cmd in (0x05,0x07,0x08,0x81,0x82,0x83,0x84,0x85):
    h=hid.device(); h.open_path(path)
    buf=bytearray(64); buf[0]=0x04; buf[3]=cmd; buf[4]=0; buf[5]=0
    checksum(buf)
    try:
        h.write(bytes(buf)); time.sleep(0.25)
    except Exception as e:
        print("cmd",hex(cmd),"write err",e); h.close(); continue
    got=[]
    end=time.time()+0.8
    while time.time()<end:
        r=h.read(64,timeout_ms=100)
        if r: got.append(bytes(r))
    print("cmd",hex(cmd),"resp",[g[:20].hex(" ") for g in got])
    h.close()
