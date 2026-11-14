"""Read-only diagnostic for ASUS ROG mice.

Run while the mouse is connected by cable or through its 2.4 GHz receiver:

    .venv\\Scripts\\python probe_rog.py

Nothing is written to the mouse. The script prints the HID interfaces that
Windows exposes and the answers to the read commands, which makes it easy to
tell a wrong interface apart from a sleeping mouse.
"""

from __future__ import annotations

import sys

import hid

from batterytray.drivers import asusmouse


def describe_interfaces() -> None:
    """Lists every ASUS HID interface, including the ignored ones."""
    print("=== ASUS HID interfaces ===")
    devices = hid.enumerate(asusmouse.ASUS_VID)
    if not devices:
        print("  none. Connect the mouse by cable or the 2.4 GHz receiver.")
        return
    for dev in devices:
        path = asusmouse._path_text(dev.get("path", ""))
        marker = " <- control" if asusmouse._is_control_interface(dev) else ""
        print(f"  PID 0x{dev.get('product_id', 0):04X} "
              f"usage_page=0x{dev.get('usage_page', 0):04X} "
              f"usage=0x{dev.get('usage', 0):02X} "
              f"{dev.get('product_string') or ''}{marker}")
        print(f"    {path}")


def probe(controller: asusmouse.AsusMouseController) -> None:
    """Runs the read-only commands and prints their answers."""
    print(f"\n=== {controller.name} "
          f"(PID 0x{controller.product_id:04X}, report id "
          f"0x{controller.report_id:02X}) ===")

    try:
        percent, charging = controller.get_battery()
        print(f"  battery: {percent}%  charging={charging}")
    except asusmouse.AsusMouseError as exc:
        print(f"  battery: {exc}")

    try:
        profile, stage = controller.get_profile()
        print(f"  profile: {profile}  DPI stage: {stage}")
    except asusmouse.AsusMouseError as exc:
        print(f"  profile: {exc}")

    try:
        rate = controller.get_polling_rate()
        print(f"  polling rate: {rate} Hz")
    except asusmouse.AsusMouseError as exc:
        print(f"  polling rate: {exc}")

    try:
        stages = controller.get_dpi_stages()
        for index, stage in enumerate(stages, start=1):
            print(f"  DPI {index}: {stage.dpi_x} x {stage.dpi_y}")
    except asusmouse.AsusMouseError as exc:
        print(f"  DPI: {exc}")

    try:
        for button in controller.list_buttons():
            mapping = controller.get_button_mapping(button)
            print(f"  button 0x{mapping.button_id:04X}: "
                  f"0x{mapping.action_code:04X} ({mapping.label})")
    except asusmouse.AsusMouseError as exc:
        print(f"  buttons: {exc}")


def main() -> int:
    """Probes every control interface that responds."""
    describe_interfaces()
    candidates = asusmouse._candidate_interfaces()
    if not candidates:
        print("\nNo control interface found. The mouse may be in Bluetooth "
              "mode; this protocol only works over USB or 2.4 GHz.")
        return 1

    answered = False
    for dev in candidates:
        path = dev["path"]
        if isinstance(path, bytes):
            path = path.decode("utf-8", errors="replace")
        try:
            controller = asusmouse.AsusMouseController(
                path,
                dev["product_id"],
                asusmouse._device_name(dev["product_id"],
                                       dev.get("product_string") or ""),
                asusmouse._report_id_for(dev["product_id"]))
        except asusmouse.AsusMouseError as exc:
            print(f"\nCannot open PID 0x{dev['product_id']:04X}: {exc}")
            continue
        try:
            probe(controller)
            answered = True
        finally:
            controller.close()

    return 0 if answered else 1


if __name__ == "__main__":
    sys.exit(main())
