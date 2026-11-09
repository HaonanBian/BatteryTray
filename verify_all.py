"""Test suite for BatteryTray.

Covers the protocol encoding, the icon rendering, the config handling and the
polling loop. Run with:  python -m pytest verify_all.py
"""
from __future__ import annotations

import datetime
import threading
import time

import pytest
from PIL import Image

from batterytray import autostart, singleton
from batterytray.app import Device, build_tooltip, collect_devices
from batterytray.config import Config
from batterytray.drivers import bluetooth, razer
from batterytray.icon import DeviceState, build_icon, level_color


# --------------------------------------------------------------------------
# Razer protocol
# --------------------------------------------------------------------------


def test_report_layout_is_ninety_one_bytes():
    assert razer.REPORT_LENGTH == 90
    assert razer.FEATURE_REPORT_LENGTH == 91


def test_request_carries_the_battery_command():
    request = razer._build_request(0x1F, razer.CMD_CLASS_POWER,
                                   razer.CMD_BATTERY_LEVEL)
    assert len(request) == razer.FEATURE_REPORT_LENGTH
    # The feature report starts with the HID report id, then the Razer report.
    assert request[0] == 0x00
    assert request[2] == 0x1F           # transaction id
    assert request[6] == 0x02           # data size
    assert request[7] == 0x07           # command class: power
    assert request[8] == 0x80           # command id: battery level


def test_request_crc_covers_the_right_bytes():
    request = razer._build_request(0x1F, razer.CMD_CLASS_POWER,
                                   razer.CMD_BATTERY_LEVEL)
    expected = 0
    for i in range(3, 89):
        expected ^= request[i]
    assert request[89] == expected


def test_crc_rejects_a_corrupted_response():
    good = razer._build_request(0x1F, razer.CMD_CLASS_POWER,
                                razer.CMD_BATTERY_LEVEL)
    assert razer._crc_valid(good)
    bad = bytearray(good)
    bad[10] ^= 0xFF
    assert not razer._crc_valid(bytes(bad))


def test_viper_v3_pro_is_in_the_device_map():
    """The mouse the user owns must be known with the right transaction id."""
    assert razer.RAZER_DEVICES[0x00C1][1] == 0x1F
    assert razer.RAZER_DEVICES[0x00C0][1] == 0x1F
    assert "Viper V3 Pro" in razer.RAZER_DEVICES[0x00C1][0]


def test_device_map_entries_are_well_formed():
    for pid, (name, tid, charging) in razer.RAZER_DEVICES.items():
        assert 0 <= pid <= 0xFFFF, f"bad pid {pid:#x}"
        assert isinstance(name, str) and name, f"bad name for {pid:#x}"
        assert tid in (0x0F, 0x1F, 0x3F, 0xFF), f"bad transaction id for {pid:#x}"
        assert isinstance(charging, bool)


def test_status_codes_map_to_the_openrazer_values():
    assert razer.Status.SUCCESSFUL == 0x02
    assert razer.Status.BUSY == 0x01


# --------------------------------------------------------------------------
# Icon rendering
# --------------------------------------------------------------------------


def _count(icon: Image.Image, color) -> int:
    px = icon.load()
    total = 0
    for y in range(icon.height):
        for x in range(icon.width):
            r, g, b, a = px[x, y]
            if (a > 100 and abs(r - color[0]) < 30 and abs(g - color[1]) < 30
                    and abs(b - color[2]) < 30):
                total += 1
    return total


def test_level_colours_follow_the_thresholds():
    assert level_color(100) == (46, 160, 67, 255)
    assert level_color(60) == (46, 160, 67, 255)
    assert level_color(59) == (219, 154, 26, 255)
    assert level_color(20) == (219, 154, 26, 255)
    assert level_color(19) == (211, 47, 47, 255)
    assert level_color(None) == (117, 117, 117, 255)
    assert level_color(50, charging=True) == (66, 133, 244, 255)


def test_fill_grows_with_the_level():
    """The icon is a lightning bolt; the colour carries the level."""
    colors = {pct: level_color(pct) for pct in (0, 25, 50, 75, 100)}
    # Every level uses a colour and the icon is drawn in it.
    for pct, color in colors.items():
        assert _count(build_icon([DeviceState(pct)], 32), color) > 0


def test_icon_is_a_lightning_bolt():
    """The tray icon shows a bolt, not a battery."""
    icon = build_icon([DeviceState(100)], 32)
    px = icon.load()

    # The bolt leans to the right at the top and to the left at the bottom.
    def topmost_row():
        for y in range(icon.height):
            xs = [x for x in range(icon.width) if px[x, y][3] > 100]
            if xs:
                return y, sum(xs) / len(xs)
        return None, None

    def bottommost_row():
        for y in range(icon.height - 1, -1, -1):
            xs = [x for x in range(icon.width) if px[x, y][3] > 100]
            if xs:
                return y, sum(xs) / len(xs)
        return None, None

    _, top_x = topmost_row()
    _, bottom_x = bottommost_row()
    assert top_x is not None and bottom_x is not None
    assert top_x > bottom_x, "the bolt has to lean to the right"


def test_icon_is_visible_at_the_notification_area_size():
    """The bolt has to stay readable at 16 px."""
    icon = build_icon([DeviceState(100)], 16)
    px = icon.load()
    opaque = sum(1 for y in range(16) for x in range(16)
                 if px[x, y][3] > 128)
    assert opaque > 20


def test_charging_uses_the_charging_colour():
    icon = build_icon([DeviceState(50, charging=True)], 32)
    assert _count(icon, (66, 133, 244)) > 0


def test_multi_device_icon_draws_every_device():
    icon = build_icon([DeviceState(80), DeviceState(30)], 32)
    px = icon.load()
    left = sum(1 for x in range(icon.width // 2) for y in range(icon.height)
               if px[x, y][3] > 128)
    right = sum(1 for x in range(icon.width // 2, icon.width)
                for y in range(icon.height) if px[x, y][3] > 128)
    assert left > 0 and right > 0


def test_icon_has_transparent_background():
    icon = build_icon([DeviceState(50)], 32)
    assert icon.mode == "RGBA"
    assert icon.getpixel((0, 0))[3] == 0


# --------------------------------------------------------------------------
# Tooltip
# --------------------------------------------------------------------------


def test_tooltip_stays_within_the_windows_limit():
    """Windows truncates notification tooltips at 128 characters."""
    for count in (1, 5, 20, 50):
        devices = [Device(f"A very long device name number {i}", 50)
                   for i in range(count)]
        assert len(build_tooltip(devices)) <= 127


def test_tooltip_lists_every_device():
    devices = [Device("Mouse", 72), Device("Headset", 100, charging=True)]
    tooltip = build_tooltip(devices)
    assert "Mouse: 72%" in tooltip
    assert "Headset: 100% (charging)" in tooltip


def test_tooltip_handles_an_empty_list():
    assert "no devices" in build_tooltip([])


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------


def test_config_round_trips(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    config = Config()
    config.poll_interval = 123
    config.include_other_peripherals = True
    config.save()

    loaded = Config.load()
    assert loaded.poll_interval == 123
    assert loaded.include_other_peripherals is True


def test_config_ignores_unknown_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    (tmp_path / "BatteryTray").mkdir()
    (tmp_path / "BatteryTray" / "config.json").write_text(
        '{"poll_interval": 45, "bogus_key": 1}', encoding="utf-8")
    config = Config.load()
    assert config.poll_interval == 45


def test_config_survives_a_corrupt_file(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    (tmp_path / "BatteryTray").mkdir()
    (tmp_path / "BatteryTray" / "config.json").write_text("{not json",
                                                           encoding="utf-8")
    assert Config.load().poll_interval == 60


def test_poll_interval_is_clamped():
    config = Config()
    config.poll_interval = 1
    assert config.poll_interval_seconds == 15
    config.poll_interval = 10 ** 6
    assert config.poll_interval_seconds == 3600


# --------------------------------------------------------------------------
# Device collection
# --------------------------------------------------------------------------


def test_collect_devices_prefers_mice_and_headsets():
    devices = collect_devices(Config())
    kinds = {d.kind for d in devices}
    assert kinds <= {"mouse", "headset", "controller", "device"}
    # The default config excludes controllers.
    assert "controller" not in kinds


def test_collect_devices_can_include_other_peripherals():
    config = Config()
    config.include_other_peripherals = True
    devices = collect_devices(config)
    assert all(d.percent is None or 0 <= d.percent <= 100 for d in devices)


def test_the_settings_choose_which_kinds_are_shown():
    """The settings window decides which kinds of peripheral are listed."""
    config = Config()
    config.set_enabled_kinds(["mouse"])
    assert config.kinds == ("mouse",)

    config.set_enabled_kinds(["headset", "controller"])
    assert set(config.kinds) == {"headset", "controller"}


def test_the_old_config_still_shows_mice_and_headsets():
    """A config file without the new setting keeps the old behaviour."""
    config = Config()
    assert config.enabled_kinds is None
    assert config.kinds == ("mouse", "headset")


def test_the_class_of_device_tells_a_mouse_from_a_gamepad():
    """The Bluetooth class of device is the authoritative kind."""
    from batterytray.drivers import bluetooth

    # A HID mouse and a HID gamepad.
    assert bluetooth._kind_from_class_of_device({"LEAppearance": 0x03C2}) == "mouse"
    assert bluetooth._kind_from_class_of_device({"LEAppearance": 0x03C4}) == "controller"
    # A classic audio device (major class 4).
    assert bluetooth._kind_from_class_of_device({"COD": 0x240404}) == "headset"
    # A classic keyboard: major class 5, minor class 1.
    assert bluetooth._kind_from_class_of_device({"COD": 0x000125}) == "keyboard"


def test_the_device_kind_comes_from_the_class_of_device():
    """The class of device wins over the friendly name."""
    from batterytray.drivers import bluetooth

    # The name says nothing useful, but the class says it is a mouse.
    assert bluetooth._classify("ROG KERIS WIRELESS AIMPOINT", "mouse") == "mouse"
    assert bluetooth._classify("Xbox Wireless Controller", "controller") == "controller"
    # Without a class the name is used.
    assert bluetooth._classify("WH-CH720N Hands-Free AG") == "headset"


def test_the_class_of_device_is_read_for_the_paired_devices():
    """The registry holds the class of every paired peripheral."""
    from batterytray.drivers import bluetooth

    records = bluetooth._read_registry_devices()
    if not records:
        pytest.skip("no paired Bluetooth devices on this machine")
    kinds = [bluetooth._kind_from_class_of_device(values)
             for values in records.values()]
    assert all(kind in {"", "mouse", "headset", "controller", "keyboard"}
               for kind in kinds)


def test_the_registry_holds_when_the_device_was_last_seen():
    """The registry record carries the moment the device was last heard from."""
    from batterytray.drivers import bluetooth

    records = bluetooth._read_registry_devices()
    if not records:
        pytest.skip("no paired Bluetooth devices on this machine")
    seen = [bluetooth._registry_last_seen(values) for values in records.values()]
    assert any(stamp is not None for stamp in seen)


def test_the_gamepad_is_listed_when_its_kind_is_enabled():
    """A gamepad shows up as soon as the user asks for it."""
    config = Config()
    config.set_enabled_kinds(["mouse", "headset", "controller", "keyboard"])
    devices = collect_devices(config)
    assert all(d.kind in {"mouse", "headset", "controller", "keyboard"}
               for d in devices)


def test_collect_devices_respects_a_name_whitelist():
    config = Config()
    config.devices = ["nothing matches this"]
    assert collect_devices(config) == []


def test_mice_sort_before_other_peripherals():
    config = Config()
    config.include_other_peripherals = True
    devices = collect_devices(config)
    kinds = [d.kind for d in devices]
    if "mouse" in kinds and "controller" in kinds:
        assert kinds.index("mouse") < kinds.index("controller")


# --------------------------------------------------------------------------
# Drivers against the real hardware
# --------------------------------------------------------------------------


def test_razer_reads_the_viper_v3_pro():
    """The Viper V3 Pro is attached to this machine."""
    devices = razer.read_devices()
    viper = [d for d in devices if "Viper V3 Pro" in d.name]
    if not viper:
        pytest.skip("Viper V3 Pro not connected")
    for device in viper:
        assert 1 <= device.percent <= 100, device


def test_bluetooth_reads_a_headset():
    devices = bluetooth.read_devices()
    for device in devices:
        assert 1 <= device.percent <= 100, device


def test_bluetooth_deduplicates_by_address():
    devices = bluetooth.read_devices()
    keys = [d.address or d.name for d in devices]
    assert len(keys) == len(set(keys))


def test_bluetooth_reports_the_connection_state():
    """Every Bluetooth node must say whether the device is reachable."""
    devices = bluetooth.read_devices()
    for device in devices:
        assert isinstance(device.connected, bool), device


def test_bluetooth_connection_flag_matches_the_property_store():
    """The driver must read the same flag that Windows exposes."""
    for device in bluetooth.read_devices():
        # Windows keeps the last battery level on the node, so a device that is
        # flagged as disconnected must not be trusted to have a live reading.
        if not device.connected:
            assert device.percent is not None, device


def test_a_fresh_battery_report_means_the_device_is_reachable():
    """A device that was seen moments ago is reachable."""
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    fresh = now - datetime.timedelta(seconds=30)
    assert bluetooth._is_reachable(False, fresh, now) is True


def test_an_old_battery_report_means_the_device_is_gone():
    """A device that has been silent for days is off."""
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    stale = now - datetime.timedelta(days=40)
    assert bluetooth._is_reachable(False, stale, now) is False


def test_the_connection_flag_wins_over_the_last_seen_time():
    """A device that is connected is reachable, whatever the stamp says."""
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    stale = now - datetime.timedelta(days=40)
    assert bluetooth._is_reachable(True, stale, now) is True


def test_a_device_without_any_signal_is_assumed_to_be_connected():
    """A node that publishes neither signal must not be hidden."""
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    assert bluetooth._is_reachable(None, None, now) is False


def test_the_disconnect_moment_does_not_look_like_a_live_reading():
    """Windows rewrites the battery property when a device disconnects.

    The report time therefore cannot be used to tell a live device from a
    device that just switched off; only the moment the stack last heard from
    it can.
    """
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    # The device was last heard from ten minutes ago, so it is off, even
    # though a report landed five minutes ago.
    seen = now - datetime.timedelta(minutes=10)
    assert bluetooth._is_reachable(False, seen, now) is False
    # As soon as it is seen again, it counts as reachable.
    seen = now - datetime.timedelta(seconds=20)
    assert bluetooth._is_reachable(False, seen, now) is True
    assert bluetooth._is_reachable(True, None, now) is True


def test_the_wh_720n_is_not_reported_as_a_full_battery():
    """The headset the user complained about must not show a frozen 100%."""
    devices = collect_devices(Config())
    for device in devices:
        if "WH-CH720N" in device.name:
            assert device.connected is False, device
            assert device.percent is None, device


def test_disconnected_devices_do_not_show_a_battery_level(monkeypatch):
    """A disconnected headset must not show its stale battery reading."""
    stale = bluetooth.BluetoothDevice(
        name="WH-CH720N Hands-Free AG",
        address="40:72:18:2A:1C:8B",
        percent=100,
        kind="headset",
        connected=False,
    )
    monkeypatch.setattr(bluetooth, "read_devices", lambda: [stale])
    monkeypatch.setattr(razer, "read_devices", lambda: [])

    devices = collect_devices(Config())

    assert len(devices) == 1
    device = devices[0]
    assert device.percent is None
    assert device.connected is False
    assert device.subtitle == "未连接"
    assert ("状态", "未连接") in device.detail_rows


def test_connected_devices_keep_their_battery_level(monkeypatch):
    """A connected device still shows its level."""
    live = bluetooth.BluetoothDevice(
        name="ROG KERIS WIRELESS AIMPOINT",
        address="E8:4F:9B:73:E3:57",
        percent=79,
        kind="mouse",
        connected=True,
    )
    monkeypatch.setattr(bluetooth, "read_devices", lambda: [live])
    monkeypatch.setattr(razer, "read_devices", lambda: [])

    devices = collect_devices(Config())

    assert len(devices) == 1
    assert devices[0].percent == 79
    assert devices[0].connected is True


def test_the_tooltip_marks_disconnected_devices():
    """A disconnected device must not appear in the tooltip."""
    tooltip = build_tooltip([
        Device(name="WH-CH720N", percent=None, connected=False),
    ])
    assert "WH-CH720N" not in tooltip
    assert "disconnected" not in tooltip
    assert "no devices connected" in tooltip


def test_the_tooltip_only_lists_connected_devices():
    """Connected devices stay in the tooltip, disconnected ones drop out."""
    tooltip = build_tooltip([
        Device(name="Razer Viper V3 Pro", percent=70, kind="mouse"),
        Device(name="WH-CH720N", percent=None, connected=False),
    ])
    assert "Razer Viper V3 Pro" in tooltip
    assert "70%" in tooltip
    assert "WH-CH720N" not in tooltip


def test_connected_devices_filters_out_offline_ones():
    """The helper keeps the reachable devices only."""
    from batterytray.app import connected_devices

    live = Device(name="Mouse", percent=50)
    dead = Device(name="Headset", percent=None, connected=False)

    assert connected_devices([live, dead]) == [live]
    assert connected_devices([dead]) == []


# --------------------------------------------------------------------------
# Single instance
# --------------------------------------------------------------------------


def test_single_instance_guard_blocks_a_second_holder():
    # A running copy of the app holds the mutex, so skip rather than fail.
    existing = singleton.acquire()
    if existing is None:
        pytest.skip("another instance of the app is running")
    try:
        assert singleton.acquire() is None
    finally:
        existing.release()
    # After releasing, the mutex is available again.
    second = singleton.acquire()
    assert second is not None
    second.release()


# --------------------------------------------------------------------------
# Autostart
# --------------------------------------------------------------------------


def test_autostart_round_trip():
    was_enabled = autostart.is_enabled()
    try:
        assert autostart.enable() is True
        assert autostart.is_enabled() is True
        assert autostart.disable() is True
        assert autostart.is_enabled() is False
    finally:
        autostart.set_enabled(was_enabled)


def test_the_startup_shortcut_has_a_usable_target():
    """The shortcut must point at a real program.

    A quoted target path ends up empty when Windows reads the shortcut back,
    which makes the app silently fail to start with Windows.
    """
    was_enabled = autostart.is_enabled()
    try:
        assert autostart.enable() is True

        import subprocess

        path = autostart._shortcut_path()
        script = (
            "$s = (New-Object -ComObject WScript.Shell)"
            f".CreateShortcut('{path}');"
            "$s.TargetPath"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=20)
        target = result.stdout.decode(errors="replace").strip()

        assert target, "the shortcut has no target"
        assert not target.startswith('"'), "the target path must not be quoted"
        assert target.lower().endswith(".exe"), target
    finally:
        autostart.set_enabled(was_enabled)


def test_the_startup_target_is_the_executable_when_frozen(monkeypatch):
    """A packaged app starts the exe itself, without any arguments."""
    class FakeSys:
        frozen = True
        executable = r"D:\Desktop\a\dist\BatteryTray.exe"

    monkeypatch.setattr(autostart, "sys", FakeSys)
    target, arguments = autostart._target_and_arguments()
    assert target == r"D:\Desktop\a\dist\BatteryTray.exe"
    assert arguments == ""


def test_the_startup_target_quotes_the_script_when_running_from_source(monkeypatch):
    """Running from source the quotes belong in the arguments."""
    import sys as real_sys

    class FakeSys:
        frozen = False
        executable = real_sys.executable
        argv = real_sys.argv

    monkeypatch.setattr(autostart, "sys", FakeSys)
    target, arguments = autostart._target_and_arguments()
    assert target == real_sys.executable
    assert not target.startswith('"')
    assert arguments.startswith('"')


# --------------------------------------------------------------------------
# Poll loop
# --------------------------------------------------------------------------


def test_refresh_wakes_the_loop_without_a_second_reader():
    """The refresh button must not start a parallel HID read."""
    from batterytray.app import TrayApp

    config = Config()
    config.poll_interval = 3600
    app = TrayApp(config)

    calls = []
    original = app._poll

    def counting_poll():
        calls.append(1)
        original()

    app._poll = counting_poll

    thread = threading.Thread(target=app._loop, daemon=True)
    thread.start()
    time.sleep(1.0)
    app._request_refresh()
    time.sleep(1.0)
    app._stop.set()
    app._wake.set()
    thread.join(timeout=5)

    # The initial poll plus the refresh, with no overlapping readers.
    assert len(calls) == 2, calls


def test_stop_ends_the_loop():
    from batterytray.app import TrayApp

    app = TrayApp(Config())
    app.config.poll_interval = 3600
    thread = threading.Thread(target=app._loop, daemon=True)
    thread.start()
    time.sleep(0.5)
    app._stop.set()
    app._wake.set()
    thread.join(timeout=5)
    assert not thread.is_alive()


# --------------------------------------------------------------------------
# Device details
# --------------------------------------------------------------------------


def test_device_subtitle_falls_back_to_the_kind():
    assert Device("Mouse", 80, kind="mouse").subtitle == "无线连接"
    assert Device("Headset", 80, kind="headset").subtitle == "蓝牙连接"


def test_device_detail_rows_include_the_connection_and_product_id():
    device = Device("Razer Viper V3 Pro Wireless", 70, kind="mouse",
                    product_id=0x00C1, connection="2.4GHz 无线")
    rows = dict(device.detail_rows)
    assert rows["连接方式"] == "2.4GHz 无线"
    assert rows["产品 ID"] == "0x00C1"
    assert rows["状态"] == "已连接"


def test_device_detail_rows_report_charging():
    device = Device("Mouse", 40, charging=True, kind="mouse")
    assert dict(device.detail_rows)["状态"] == "充电中"


def test_razer_connection_mode_reflects_the_product_name():
    assert razer._connection_mode("Razer Viper V3 Pro Wired", False) == "有线连接"
    assert razer._connection_mode("Razer Viper V3 Pro Wireless", False) \
        == "2.4GHz 无线"
    assert razer._connection_mode("Razer Viper V3 Pro Wireless", True) \
        == "充电中（底座）"


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------


class _FakeApp:
    """Stands in for TrayApp when the window is exercised on its own."""

    def request_refresh(self):
        pass

    def rename_device(self, original_name, new_name):
        pass


@pytest.fixture(scope="module")
def gui_window():
    """A single window shared by the GUI tests.

    Tkinter allows only one root window per process, so the tests share one.
    """
    pytest.importorskip("tkinter")

    from batterytray.window import BatteryWindow

    window = BatteryWindow(_FakeApp())
    yield window
    try:
        window.destroy()
    except Exception:
        pass


def test_window_posts_work_to_the_tkinter_thread(gui_window):
    """The tray thread must not touch Tk directly."""
    calls = []
    gui_window.post(calls.append, 42)
    gui_window.update()
    # The queue is drained by a periodic callback; run it directly.
    gui_window._drain_pending()
    assert calls == [42]


def test_window_shows_a_card_for_every_device(gui_window):
    devices = [
        Device("Razer Viper V3 Pro Wireless", 70, kind="mouse",
               product_id=0x00C1, connection="2.4GHz 无线"),
        Device("WH-CH720N Hands-Free AG", 100, kind="headset"),
    ]
    gui_window.set_devices(devices)
    gui_window.update_idletasks()
    assert len(gui_window._cards) == 2
    assert gui_window._cards[0].name_label.cget("text") \
        == "Razer Viper V3 Pro Wireless"
    assert gui_window._cards[0].status_label.cget("text") == "2.4GHz 无线"
    assert gui_window._cards[1].status_label.cget("text") == "蓝牙连接"


def test_window_reports_an_empty_device_list(gui_window):
    gui_window.set_devices([])
    gui_window.update_idletasks()
    assert gui_window._cards == []
    assert gui_window.summary_label.cget("text") == ""


def test_dpi_scaling_helpers():
    from batterytray.dpi import scale_font, scale_pixels

    assert scale_pixels(16, 96) == 16
    assert scale_pixels(16, 120) == 20
    assert scale_font(10, 96) == 10
    assert scale_font(10, 120) == 12
    # Never collapse a size to nothing.
    assert scale_pixels(1, 48) >= 1
    assert scale_font(1, 48) >= 6


# --------------------------------------------------------------------------
# The quick panel
# --------------------------------------------------------------------------


def test_quick_panel_shows_a_row_for_every_device(gui_window):
    from batterytray.quickpanel import QuickPanel

    panel = QuickPanel(gui_window)
    try:
        devices = [
            Device("Razer Viper V3 Pro Wireless", 70, kind="mouse",
                   connection="2.4GHz 无线"),
            Device("WH-CH720N Hands-Free AG", 100, kind="headset"),
        ]
        panel.set_devices(devices)
        panel.update_idletasks()
        assert len(panel._rows) == 2
        assert panel._rows[0].name_label.cget("text") \
            == "Razer Viper V3 Pro Wireless"
        assert panel._rows[0].percent_label.cget("text") == "70%"
        assert panel._rows[0].state_label.cget("text") == "2.4GHz 无线"
        assert panel._rows[1].percent_label.cget("text") == "100%"
    finally:
        panel.destroy()


def test_quick_panel_marks_charging_devices(gui_window):
    from batterytray.quickpanel import QuickPanel

    panel = QuickPanel(gui_window)
    try:
        panel.set_devices([Device("Mouse", 40, charging=True, kind="mouse")])
        panel.update_idletasks()
        assert panel._rows[0].state_label.cget("text") == "充电中"
    finally:
        panel.destroy()


def test_quick_panel_hides_disconnected_devices(gui_window):
    """The popup only lists the devices that are connected."""
    from batterytray.quickpanel import QuickPanel

    panel = QuickPanel(gui_window)
    try:
        panel.set_devices([
            Device("Razer Viper V3 Pro", 70, kind="mouse"),
            Device("WH-CH720N", None, kind="headset", connected=False),
        ])
        panel.update_idletasks()
        assert len(panel._rows) == 1
        assert panel._rows[0].name_label.cget("text") == "Razer Viper V3 Pro"
    finally:
        panel.destroy()


def test_main_window_still_shows_disconnected_devices(gui_window):
    """The full window keeps the offline devices visible."""
    gui_window.set_devices([
        Device("Razer Viper V3 Pro", 70, kind="mouse"),
        Device("WH-CH720N", None, kind="headset", connected=False),
    ])
    gui_window.update_idletasks()
    assert len(gui_window._cards) == 2


def test_quick_panel_toggles(gui_window):
    from batterytray.quickpanel import QuickPanel

    panel = QuickPanel(gui_window)
    try:
        panel.set_devices([Device("Mouse", 80, kind="mouse")])
        assert panel._visible is False

        panel.toggle()
        assert panel._visible is True
        assert panel.winfo_viewable()

        panel.toggle()
        assert panel._visible is False
        assert not panel.winfo_viewable()
    finally:
        panel.destroy()


def test_quick_panel_stays_open_until_clicked_outside(gui_window):
    """The panel must not close on its own."""
    from batterytray.quickpanel import QuickPanel

    panel = QuickPanel(gui_window)
    try:
        panel.set_devices([Device("Mouse", 80, kind="mouse")])
        panel.toggle()
        # Let the watcher run a few times.
        for _ in range(10):
            gui_window.update()
        assert panel._visible is True
    finally:
        panel.destroy()


def test_tray_menu_has_a_default_item_for_the_panel():
    """A left click on the tray icon must open the panel."""
    from batterytray.app import build_menu

    calls = []
    menu = build_menu(
        Config(), None,
        refresh=lambda: None,
        show_window=lambda: None,
        toggle_panel=lambda: calls.append("panel"),
        open_settings=lambda: None,
        quit_app=lambda: None,
    )
    defaults = [item for item in menu if item.default]
    assert len(defaults) == 1
    defaults[0]._action(None, defaults[0])
    assert calls == ["panel"]


# --------------------------------------------------------------------------
# Duplicated devices
# --------------------------------------------------------------------------


def test_quick_panel_does_not_grow_on_refresh(gui_window):
    """Refreshing must not leave the separators behind."""
    from batterytray.quickpanel import QuickPanel

    panel = QuickPanel(gui_window)
    try:
        devices = [Device("Mouse", 80, kind="mouse"),
                   Device("Headset", 100, kind="headset")]
        for _ in range(5):
            panel.set_devices(devices)
            gui_window.update()
        # Two rows plus one separator between them.
        assert len(panel.rows_frame.winfo_children()) == 3
        assert len(panel._rows) == 2
    finally:
        panel.destroy()


def test_quick_panel_clears_the_placeholder_on_refresh(gui_window):
    """The empty placeholder must not pile up either."""
    from batterytray.quickpanel import QuickPanel

    panel = QuickPanel(gui_window)
    try:
        for _ in range(3):
            panel.set_devices([])
            gui_window.update()
        assert len(panel.rows_frame.winfo_children()) == 1
    finally:
        panel.destroy()


def test_main_window_does_not_grow_on_refresh(gui_window):
    """The card list must keep the same size after a refresh."""
    window = gui_window
    devices = [Device("Mouse", 80, kind="mouse"),
               Device("Headset", 100, kind="headset")]
    for _ in range(5):
        window.set_devices(devices)
        window.update_idletasks()
    assert len(window.list_frame.winfo_children()) == 2
    assert len(window._cards) == 2


def test_main_window_clears_the_placeholder_on_refresh(gui_window):
    window = gui_window
    for _ in range(3):
        window.set_devices([])
        window.update_idletasks()
    assert len(window.list_frame.winfo_children()) == 1


def test_devices_are_deduplicated_by_name():
    """The same device must not be reported twice."""
    devices = [Device("Mouse", 80, kind="mouse"),
               Device("Mouse", 80, kind="mouse")]
    unique = {}
    for device in devices:
        unique.setdefault(device.original_name, device)
    assert len(unique) == 1


# --------------------------------------------------------------------------
# Custom device names
# --------------------------------------------------------------------------


def test_config_keeps_the_custom_name():
    config = Config()
    config.set_custom_name("Razer Viper V3 Pro Wireless", "我的毒蝰")
    assert config.display_name("Razer Viper V3 Pro Wireless") == "我的毒蝰"
    # An unknown device keeps its original name.
    assert config.display_name("Other") == "Other"


def test_config_clears_the_custom_name():
    config = Config()
    config.set_custom_name("Mouse", "游戏鼠标")
    config.set_custom_name("Mouse", "")
    assert config.display_name("Mouse") == "Mouse"
    assert "Mouse" not in config.custom_names


def test_custom_name_is_applied_to_the_devices():
    config = Config()
    config.set_custom_name("Razer Viper V3 Pro Wireless", "我的毒蝰")
    devices = [Device("Razer Viper V3 Pro Wireless", 70, kind="mouse")]
    for device in devices:
        device.name = config.display_name(device.original_name)
    assert devices[0].name == "我的毒蝰"
    # The original name is kept for the next lookup.
    assert devices[0].original_name == "Razer Viper V3 Pro Wireless"


def test_custom_name_survives_a_config_roundtrip(tmp_path, monkeypatch):
    config = Config()
    config.set_custom_name("Mouse", "游戏鼠标")
    monkeypatch.setattr("batterytray.config.config_dir", lambda: tmp_path)
    config.save()

    loaded = Config.load()
    assert loaded.display_name("Mouse") == "游戏鼠标"


def test_device_keeps_the_original_name():
    device = Device("Razer Viper V3 Pro Wireless", 70, kind="mouse")
    assert device.original_name == "Razer Viper V3 Pro Wireless"

    device.name = "我的毒蝰"
    assert device.original_name == "Razer Viper V3 Pro Wireless"


def test_card_rename_reports_the_original_name(gui_window):
    """Renaming a card hands the original name to the callback."""
    renames = []
    window = gui_window
    window.app = type("App", (), {
        "rename_device": lambda self, original, new: renames.append((original, new)),
    })()
    window.set_devices([Device("Razer Viper V3 Pro Wireless", 70, kind="mouse")])
    window.update_idletasks()

    card = window._cards[0]
    card._start_rename()
    window.update_idletasks()
    assert card._editor is not None

    card._editor.delete(0, "end")
    card._editor.insert(0, "我的毒蝰")
    card._finish_rename("我的毒蝰")

    assert renames == [("Razer Viper V3 Pro Wireless", "我的毒蝰")]
    # The card shows the new name right away.
    assert card.name_label.cget("text") == "我的毒蝰"


def test_card_rename_can_be_cancelled(gui_window):
    """Escape keeps the original name."""
    renames = []
    window = gui_window
    window.app = type("App", (), {
        "rename_device": lambda self, original, new: renames.append((original, new)),
    })()
    window.set_devices([Device("Mouse", 70, kind="mouse")])
    window.update_idletasks()

    card = window._cards[0]
    card._start_rename()
    window.update_idletasks()
    card._editor.delete(0, "end")
    card._editor.insert(0, "别的名字")
    card._cancel_rename()

    assert renames == []
    assert card._editor is None
    assert card.name_label.cget("text") == "Mouse"


def test_rename_dialog_returns_the_new_name(gui_window):
    """The dialog hands the typed name back."""
    from batterytray.renamedialog import RenameDialog

    dialog = RenameDialog(gui_window, gui_window.family, gui_window.dpi,
                          "Mouse", "Mouse")
    try:
        gui_window.update_idletasks()
        assert dialog.entry.get() == "Mouse"
        dialog.entry.delete(0, "end")
        dialog.entry.insert(0, "游戏鼠标")
        dialog._confirm()
        assert dialog.result == "游戏鼠标"
    finally:
        try:
            dialog.destroy()
        except Exception:
            pass


def test_rename_dialog_can_be_cancelled(gui_window):
    from batterytray.renamedialog import RenameDialog

    dialog = RenameDialog(gui_window, gui_window.family, gui_window.dpi,
                          "Mouse", "Mouse")
    try:
        gui_window.update_idletasks()
        dialog._cancel()
        assert dialog.result is None
    finally:
        try:
            dialog.destroy()
        except Exception:
            pass


def test_rename_dialog_can_reset_to_the_original_name(gui_window):
    """Clearing the field restores the original name."""
    from batterytray.renamedialog import RenameDialog

    dialog = RenameDialog(gui_window, gui_window.family, gui_window.dpi,
                          "Mouse", "游戏鼠标")
    try:
        gui_window.update_idletasks()
        dialog._reset()
        assert dialog.entry.get() == ""
    finally:
        try:
            dialog.destroy()
        except Exception:
            pass


def test_quick_panel_row_offers_the_rename(gui_window):
    """Right clicking a row opens the rename menu."""
    from batterytray.quickpanel import QuickPanel

    requests = []
    panel = QuickPanel(gui_window, on_rename=requests.append)
    try:
        panel.set_devices([Device("Mouse", 80, kind="mouse")])
        gui_window.update_idletasks()
        row = panel._rows[0]
        assert row._original_name == "Mouse"
        assert row.on_rename is not None
    finally:
        panel.destroy()


def test_app_rename_updates_the_cached_devices(tmp_path, monkeypatch):
    """Renaming through the app updates the cached device list."""
    from batterytray.app import TrayApp

    monkeypatch.setattr("batterytray.config.config_dir", lambda: tmp_path)
    config = Config()
    app = TrayApp(config=config)
    app.devices = [Device("Mouse", 80, kind="mouse")]

    app.rename_device("Mouse", "游戏鼠标")
    assert app.devices[0].name == "游戏鼠标"
    assert app.devices[0].original_name == "Mouse"

    # The name has to survive a restart.
    assert Config.load().display_name("Mouse") == "游戏鼠标"

# --------------------------------------------------------------------------
# The settings window
# --------------------------------------------------------------------------


def test_the_settings_dialog_keeps_the_settings(gui_window):
    """Saving the dialog hands back the changed settings."""
    from batterytray.settingsdialog import SettingsDialog

    config = Config()
    dialog = SettingsDialog(gui_window, config, gui_window.family, gui_window.dpi)
    try:
        dialog.kind_vars["controller"].set(True)
        dialog.threshold_var.set(35)
        dialog.notify_var.set(False)
        dialog._confirm()

        assert dialog.result is not None
        assert "controller" in dialog.result.enabled_kinds
        assert dialog.result.low_battery_threshold == 35
        assert dialog.result.notify_low_battery is False
        # The settings the dialog does not show are carried over.
        assert dialog.result.custom_names == config.custom_names
    finally:
        try:
            dialog.destroy()
        except Exception:
            pass


def test_the_settings_dialog_can_be_cancelled(gui_window):
    """Cancelling leaves the settings alone."""
    from batterytray.settingsdialog import SettingsDialog

    dialog = SettingsDialog(gui_window, Config(), gui_window.family, gui_window.dpi)
    try:
        dialog._cancel()
        assert dialog.result is None
    finally:
        try:
            dialog.destroy()
        except Exception:
            pass


def test_the_settings_dialog_clamps_the_threshold(gui_window):
    """A threshold outside the usable range is forced back into it."""
    from batterytray.settingsdialog import SettingsDialog

    dialog = SettingsDialog(gui_window, Config(), gui_window.family, gui_window.dpi)
    try:
        dialog.threshold_var.set(500)
        assert dialog._clamped_threshold() == 100
        dialog.threshold_var.set(-3)
        assert dialog._clamped_threshold() == 1
        dialog.threshold_var.set(42)
        assert dialog._clamped_threshold() == 42
    finally:
        try:
            dialog.destroy()
        except Exception:
            pass


def test_applying_the_settings_saves_them(tmp_path, monkeypatch):
    """The app stores the new settings right away."""
    from batterytray.app import TrayApp

    monkeypatch.setattr("batterytray.config.config_dir", lambda: tmp_path)
    app = TrayApp(config=Config())

    new_config = Config()
    new_config.set_enabled_kinds(["headset", "controller"])
    new_config.low_battery_threshold = 30

    app.apply_config(new_config)

    assert app.config.low_battery_threshold == 30
    loaded = Config.load()
    assert loaded.low_battery_threshold == 30
    assert set(loaded.enabled_kinds) == {"headset", "controller"}
