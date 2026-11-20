
a = Analysis(['mini.py'], pathex=[], binaries=[], datas=[],
             hiddenimports=[], hookspath=[], hooksconfig={},
             runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
          name='mini_dbg', console=True, debug=True,
          bootloader_ignore_signals=False, strip=False, upx=False)
