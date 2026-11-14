import re, pathlib
for p in [pathlib.Path(r'D:\Program Files user\BrimDeck\BrimDeck.Core.dll'), pathlib.Path(r'D:\Program Files user\BrimDeck\BrimDeck.pdb'), pathlib.Path(r'D:\Program Files user\BrimDeck\BrimDeck.Core.pdb')]:
    data=p.read_bytes()
    text=data.decode('latin1',errors='ignore')
    hits=[]
    for m in re.finditer(r'[ -~]{4,}', text):
        s=m.group()
        if any(k in s.lower() for k in ('vxe','battery','hid','320f','5088','brimdeck')):
            hits.append(s)
    print('---',p,len(data),'hits',len(hits))
    for s in hits[:120]: print(s[:200])
