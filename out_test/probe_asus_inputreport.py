"""Reads the ASUS keyboard battery report with the Windows HID API.

The Linux driver (hid-asus.c) asks the keyboard for an *input* report
with id 0x03 and 9 bytes: byte 1 is the level (0..255) and byte 8 the
charging state. hidapi cannot read input reports, but the Windows HID
API can, through ``HidD_GetInputReport``.
"""

import ctypes
import ctypes.wintypes as wt

kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
hid = ctypes.WinDLL("hid.dll", use_last_error=True)

hid.HidD_GetInputReport.restype = ctypes.c_long
hid.HidD_GetInputReport.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.ULONG]
hid.HidD_GetPreparsedData.restype = ctypes.c_long
hid.HidD_GetPreparsedData.argtypes = [wt.HANDLE, ctypes.c_void_p]
hid.HidD_FreePreparsedData.restype = ctypes.c_long
hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
hid.HidD_GetAttributes.restype = ctypes.c_long
hid.HidD_GetAttributes.argtypes = [wt.HANDLE, ctypes.c_void_p]

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = wt.HANDLE(-1).value


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Size", wt.ULONG),
        ("VendorID", wt.USHORT),
        ("ProductID", wt.USHORT),
        ("VersionNumber", wt.USHORT),
    ]


def open_device(path: str):
    handle = kernel32.CreateFileW(
        path, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
        None, OPEN_EXISTING, 0, None)
    if handle == INVALID_HANDLE_VALUE:
        raise OSError(f"CreateFile failed {ctypes.get_last_error()}")
    return handle


def main():
    import hid as hidapi

    for dev in hidapi.enumerate(0x0B05):
        path = dev.get("path")
        if not path:
            continue
        path = path.decode() if isinstance(path, bytes) else path
        page = dev.get("usage_page")
        usage = dev.get("usage")
        print(f"\n== page={page} usage={usage} ==")

        try:
            handle = open_device(path)
        except OSError as exc:
            print(f"  open failed: {exc}")
            continue

        attributes = HIDD_ATTRIBUTES()
        attributes.Size = ctypes.sizeof(attributes)
        hid.HidD_GetAttributes(handle, ctypes.byref(attributes))

        preparsed = ctypes.c_void_p()
        if hid.HidD_GetPreparsedData(handle, ctypes.byref(preparsed)):
            # the preparsed data holds the report descriptor
            hid.HidD_FreePreparsedData(preparsed)

        for report_id in range(0, 8):
            for length in (9, 10):
                buf = ctypes.create_string_buffer(length)
                buf[0] = report_id
                ctypes.set_last_error(0)
                result = hid.HidD_GetInputReport(handle, buf, length)
                if result:
                    print(f"  id={report_id} len={length} -> {result}: "
                          f"{bytes(buf.raw[:length]).hex(' ')}")
                else:
                    err = ctypes.get_last_error()
                    if err not in (0, 87):
                        print(f"  id={report_id} len={length}: error {err}")

        kernel32.CloseHandle(handle)


if __name__ == "__main__":
    main()
