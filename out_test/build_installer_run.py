import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import shutil
import build_installer as builder

root = Path(__file__).resolve().parent.parent
app_exe = root / "out_test" / "dist" / "BatteryTray.exe"
builder.DIST = root / "out_test" / "release"
installer = builder.build_installer_exe(app_exe)
setup = builder.DIST / f"BatteryTray-Setup-{builder.VERSION}.exe"
shutil.copy2(installer, setup)
archive = builder.make_portable(app_exe)
print("setup", setup.stat().st_size, "portable", archive.stat().st_size)
