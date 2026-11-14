"""Windows tray application that shows mouse and headset battery levels.

Runs as a single instance, polls every supported device on a timer, and shows
the result as a battery icon in the notification area.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass
from typing import Callable

import pystray

from . import autostart, singleton
from .config import Config, config_dir
from .drivers import asusmouse, bluetooth, razer
from .icon import DeviceState, build_device_icon, build_icon


# Device kinds, in the order the user cares about them.
KIND_MOUSE = "mouse"
KIND_HEADSET = "headset"
KIND_CONTROLLER = "controller"
KIND_KEYBOARD = "keyboard"
KIND_OTHER = "device"

# Kinds shown by default. The Xbox controller and keyboards are deliberately
# left out: the user asked for mouse and headset levels.
DEFAULT_KINDS = (KIND_MOUSE, KIND_HEADSET)


@dataclass
class Device:
    """One device the app knows about."""

    name: str
    percent: int | None
    charging: bool = False
    kind: str = KIND_OTHER
    # Extra details shown in the GUI, e.g. the USB product id.
    product_id: int | None = None
    connection: str = ""
    address: str = ""
    # The polling rate the mouse is set to, in Hz. Zero when unknown.
    polling_rate: int = 0
    # The DPI the mouse is set to. Zero when unknown.
    dpi: int = 0
    # The name reported by the device, used to look up the custom name.
    original_name: str = ""
    # ``False`` when the device is known but currently not reachable.
    connected: bool = True

    def __post_init__(self) -> None:
        if not self.original_name:
            self.original_name = self.name

    @property
    def state(self) -> DeviceState:
        return DeviceState(percent=self.percent, charging=self.charging)

    @property
    def priority(self) -> int:
        """Sort key: mice and headsets come first."""
        try:
            return DEFAULT_KINDS.index(self.kind)
        except ValueError:
            return len(DEFAULT_KINDS)

    @property
    def subtitle(self) -> str:
        """One-line summary of the connection mode."""
        if not self.connected:
            return "未连接"
        if self.connection:
            return self.connection
        if self.kind == KIND_MOUSE:
            return "无线连接"
        if self.kind == KIND_HEADSET:
            return "蓝牙连接"
        if self.kind == KIND_CONTROLLER:
            return "蓝牙连接"
        return "已连接"

    @property
    def detail_rows(self) -> list[tuple[str, str]]:
        """The key/value rows shown when a card is expanded."""
        rows: list[tuple[str, str]] = []

        # The polling rate and the DPI are only known for the mice, which
        # report them over their own protocol.
        if self.polling_rate:
            rows.append(("刷新率", f"{self.polling_rate} Hz"))
        if self.connection:
            rows.append(("连接方式", self.connection))
        if not self.connected:
            rows.append(("状态", "未连接"))
        elif self.charging:
            rows.append(("状态", "充电中"))
        else:
            rows.append(("状态", "已连接"))
        if self.dpi:
            rows.append(("DPI", str(self.dpi)))
        return rows


def collect_devices(config: Config) -> list[Device]:
    """Polls every driver and returns the devices that answered.

    Mice and headsets are reported first. Other Bluetooth peripherals (game
    controllers, keyboards) are only included when the config asks for them.
    """
    devices: list[Device] = []

    for razer_device in razer.read_devices():
        devices.append(Device(
            name=razer_device.name,
            # A sleeping mouse has no battery level to show.
            percent=razer_device.percent if razer_device.connected else None,
            charging=razer_device.charging,
            kind=KIND_MOUSE,
            product_id=razer_device.product_id,
            connection=razer_device.connection,
            polling_rate=razer_device.polling_rate,
            dpi=razer_device.dpi,
            connected=razer_device.connected,
        ))

    for asus_device in asusmouse.read_devices():
        devices.append(Device(
            name=asus_device.name,
            percent=asus_device.percent,
            charging=asus_device.charging,
            kind=KIND_MOUSE,
            product_id=asus_device.product_id,
            connection=asus_device.connection,
            polling_rate=asus_device.polling_rate,
            dpi=asus_device.dpi,
        ))

    for bt_device in bluetooth.read_devices():
        # The Razer mouse also shows up as a Bluetooth device when paired; keep
        # one entry per device by preferring the HID reading.
        if any(d.kind == KIND_MOUSE and d.name.lower() in bt_device.name.lower()
               for d in devices):
            continue
        connected = getattr(bt_device, "connected", True)
        devices.append(Device(
            name=bt_device.name,
            # A disconnected device must not show a battery bar: Windows keeps
            # the last reported level on the device node, so the number would
            # be a stale reading from the last time the device was used.
            percent=bt_device.percent if connected else None,
            charging=False,
            kind=bt_device.kind,
            address=bt_device.address,
            connection=_bluetooth_connection(bt_device),
            connected=connected,
        ))

    if config.devices:
        wanted = {name.lower() for name in config.devices}
        devices = [d for d in devices if d.name.lower() in wanted]
    else:
        # The user picks the kinds of peripheral they want to see in the
        # settings window.
        allowed = config.kinds
        devices = [d for d in devices if d.kind in allowed]
    if config.hide_disconnected:
        # The tray already leaves the unreachable devices out, so dropping
        # them here only affects the device list.
        devices = [d for d in devices if d.connected]
    # The custom name is applied last, so the lookup always uses the name the
    # device reported.
    for device in devices:
        device.name = config.display_name(device.original_name)

    devices.sort(key=lambda d: (d.priority, d.percent if d.percent is not None else 101,
                                 d.name))
    return devices


def _bluetooth_connection(device) -> str:
    """A human-readable connection mode for a Bluetooth device."""
    return "蓝牙连接"


def connected_devices(devices: list[Device]) -> list[Device]:
    """Keeps only the devices that are currently reachable.

    A device that is not connected has no meaningful battery level, so it is
    left out of the tray panel, the tooltip and the tray icon. It still shows
    up in the main window.
    """
    return [d for d in devices if d.connected]


def build_tooltip(devices: list[Device]) -> str:
    """Builds the hover text for the tray icon.

    Windows truncates the notification area tooltip at 128 characters, so the
    text is trimmed to fit.
    """
    devices = connected_devices(devices)
    if not devices:
        return "BatteryTray: no devices connected"
    lines = ["BatteryTray"]
    for device in devices:
        if device.percent is None:
            level = "unknown"
        else:
            level = f"{device.percent}%"
        if device.charging:
            level += " (charging)"
        lines.append(f"{device.name}: {level}")
    tooltip = "\n".join(lines)
    if len(tooltip) > 127:
        # Leave room for the terminator; keep the lowest-battery device, which
        # is the one the user cares about.
        tooltip = tooltip[:126] + "\u2026"
    return tooltip


def build_menu(config: Config, icon: pystray.Icon,
               refresh: Callable[[], None],
               show_window: Callable[[], None],
               toggle_panel: Callable[[], None],
               open_settings: Callable[[], None],
               quit_app: Callable[[], None]) -> pystray.Menu:
    """Builds the right-click menu."""
    autostart_item = pystray.MenuItem(
        "Start with Windows",
        lambda icon, item: _toggle_autostart(icon, item, config),
        checked=lambda item: autostart.is_enabled(),
    )
    return pystray.Menu(
        # ``default=True`` makes a left click on the tray icon pop up the
        # battery levels instead of opening the full window.
        pystray.MenuItem("查看电量", lambda icon, item: toggle_panel(),
                         default=True),
        pystray.MenuItem("打开主窗口", lambda icon, item: show_window()),
        pystray.MenuItem("立即刷新", lambda icon, item: refresh()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("设置", lambda icon, item: open_settings()),
        autostart_item,
        pystray.MenuItem("打开启动文件夹",
                         lambda icon, item: _open_startup_folder(icon, item, config)),
        pystray.MenuItem("退出", lambda icon, item: quit_app()),
    )


def _toggle_autostart(icon: pystray.Icon, item, config: Config) -> None:
    """Enables or disables the startup shortcut and saves the setting."""
    enabled = not autostart.is_enabled()
    if autostart.set_enabled(enabled):
        config.autostart = enabled
        config.save()
        icon.update_menu()


def _open_startup_folder(icon: pystray.Icon, item, config: Config) -> None:
    """Opens the Startup folder so the user can see the shortcut."""
    import os
    import subprocess

    folder = autostart.startup_folder()
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    try:
        os.startfile(str(folder))  # noqa: S606 - the user asked for it
    except (OSError, AttributeError):
        try:
            subprocess.Popen(["explorer.exe", str(folder)])
        except (OSError, subprocess.SubprocessError):
            pass


class TrayApp:
    """Owns the tray icon, the window and the polling thread."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config.load()
        self.devices: list[Device] = []
        self._icons: dict[str, pystray.Icon] = {}
        self._icon_lock = threading.Lock()
        self._window = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._lock = threading.Lock()
        self._notified: set[str] = set()
        # When set, the main window is shown as soon as the app starts.
        self.show_window_on_start = False

    def _poll(self) -> None:
        """Reads the devices and refreshes the icon and the window."""
        try:
            devices = collect_devices(self.config)
        except Exception:
            devices = []

        with self._lock:
            self.devices = devices

        self._refresh_window(devices)
        self._write_status(devices)
        self._check_low_battery(devices)

    def _refresh_window(self, devices: list[Device]) -> None:
        """Pushes the new readings into the window.

        The window lives on the tkinter thread, so the update is queued and
        picked up by the window's own main loop instead of being applied from
        the polling thread.
        """
        window = self._window
        if window is None:
            return
        try:
            window.post(self._apply_to_window, window, devices)
        except Exception:
            pass

    def _apply_to_window(self, window, devices: list[Device]) -> None:
        """Applies the readings to the window (runs on the tkinter thread)."""
        # pystray is happiest when its icons are created and updated on the
        # thread that owns the application window. Doing it from the poll
        # thread can leave icons that appear in the shell but ignore clicks.
        try:
            self._sync_tray_icons(devices)
        except Exception:
            pass
        try:
            window.set_devices(devices)
        except Exception:
            pass

    def request_refresh(self) -> None:
        """Asks the poll loop to read the devices again."""
        self._wake.set()

    def apply_config(self, config: Config) -> None:
        """Replaces the settings and refreshes everything.

        Runs on the tkinter thread. The new settings are saved right away, so
        they survive a restart even when the change was made from the
        settings window.
        """
        self.config = config
        try:
            self.config.save()
        except OSError:
            pass

        # The kinds of peripheral may have changed, so the devices have to be
        # read again.
        self.request_refresh()

    def _write_status(self, devices: list[Device]) -> None:
        """Records the latest reading so it can be inspected later."""
        lines = [f"updated {time.strftime('%Y-%m-%d %H:%M:%S')}"]
        for device in devices:
            if not device.connected:
                level = "disconnected"
            elif device.percent is None:
                level = "unknown"
            else:
                level = f"{device.percent}%"
            charging = " (charging)" if device.charging else ""
            lines.append(f"{device.name}: {level}{charging} [{device.kind}]")
        try:
            directory = config_dir()
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "status.txt").write_text(
                "\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            pass

    def _save_notification_icon(self) -> None:
        """Writes the icon used by toast notifications next to the config."""
        try:
            directory = config_dir()
            directory.mkdir(parents=True, exist_ok=True)
            build_icon([DeviceState(100)], 256).save(directory / "batterytray.png")
        except OSError:
            pass

    def _tray_devices(self, devices: list[Device]) -> list[Device]:
        """The devices that get an icon of their own.

        By default every connected device has its own icon. When the user
        turns that option off, only the device with the lowest charge is
        shown, so the notification area stays narrow.
        """
        connected = connected_devices(devices)
        if not connected:
            return []
        if self.config.show_every_device:
            return connected
        return [min(connected, key=lambda d: (d.percent is None,
                                              d.percent
                                              if d.percent is not None
                                              else 101))]

    @staticmethod
    def _icon_name(device: Device) -> str:
        """A stable, shell-safe name for one device's tray icon."""
        key = f"{device.kind}|{device.original_name}|{device.address}"
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
        return f"BatteryTray-{digest}"

    @staticmethod
    def _icon_title(device: Device) -> str:
        """The tooltip of one tray icon."""
        if not device.connected:
            level = "disconnected"
        elif device.percent is None:
            level = "unknown"
        else:
            level = f"{device.percent}%"
        if device.charging:
            level += " (charging)"
        return f"{device.name}: {level}"[:127]

    def _sync_tray_icons(self, devices: list[Device]) -> None:
        """Creates, updates and removes the per-device notification icons."""
        with self._icon_lock:
            self._sync_tray_icons_locked(devices)

    def _sync_tray_icons_locked(self, devices: list[Device]) -> None:
        selected = self._tray_devices(devices)
        wanted: dict[str, Device | None] = {}
        for device in selected:
            wanted[self._icon_name(device)] = device

        # A single muted icon keeps the app visible while no device is on.
        if not wanted:
            wanted["BatteryTray-none"] = None

        for name in list(self._icons):
            if name in wanted:
                continue
            try:
                self._icons[name].stop()
            except Exception:
                pass
            self._icons.pop(name, None)

        for name, device in wanted.items():
            if device is None:
                image = build_device_icon("device", None, connected=False,
                                          size=64)
                title = "BatteryTray: no devices connected"
            else:
                image = build_device_icon(device.kind, device.percent,
                                          device.charging, device.connected,
                                          size=64)
                title = self._icon_title(device)

            icon = self._icons.get(name)
            if icon is None:
                icon = pystray.Icon(name, icon=image, title=title)
                icon.menu = build_menu(
                    self.config, icon,
                    refresh=self._request_refresh,
                    show_window=self._show_window,
                    toggle_panel=self._toggle_panel,
                    open_settings=self._open_settings,
                    quit_app=self._quit,
                )
                icon.run_detached()
                self._icons[name] = icon
            else:
                try:
                    icon.icon = image
                    icon.title = title
                    icon.update_menu()
                except Exception:
                    # The shell may be restarting; the next poll tries again.
                    pass

    def _check_low_battery(self, devices: list[Device]) -> None:
        """Sends a Windows notification when a device gets low."""
        if not self.config.notify_low_battery:
            return
        threshold = self.config.low_battery_threshold
        for device in devices:
            if device.percent is None or device.percent > threshold:
                self._notified.discard(device.name)
                continue
            if device.name in self._notified:
                continue
            self._notified.add(device.name)
            self._notify(device)

    def _notify(self, device: Device) -> None:
        """Shows a toast notification."""
        try:
            from win10toast import ToastNotifier
        except ImportError:
            return
        try:
            toast = ToastNotifier()
            # Use the app's own icon so the toast matches the tray.
            icon_path = self._notification_icon_path()
            if icon_path:
                toast.show_toast(
                    "Battery low",
                    f"{device.name} is at {device.percent}%",
                    duration=5,
                    threaded=True,
                    icon_path=icon_path,
                )
                return
            toast.show_toast(
                "Battery low",
                f"{device.name} is at {device.percent}%",
                duration=5,
                threaded=True,
            )
        except Exception:
            # A failed notification must never disturb the polling loop.
            pass

    def _notification_icon_path(self) -> str | None:
        """Path to the icon used by toast notifications."""
        path = config_dir() / "batterytray.png"
        try:
            if path.exists():
                return str(path)
        except OSError:
            pass
        return None

    def _loop(self) -> None:
        """Polls on a timer until the app stops.

        A single thread does all the polling, so two reads never overlap on
        the HID device. The wait is interrupted by ``_request_refresh`` when
        the user asks for a refresh from the menu.
        """
        while not self._stop.is_set():
            try:
                self._poll()
            except Exception:
                # Never let an unexpected error kill the polling thread.
                pass

            if self._stop.is_set():
                break

            # Sleep until the next interval, or until a refresh is requested.
            self._wake.clear()
            self._wake.wait(self.config.poll_interval_seconds)
            self._wake.clear()

    def _request_refresh(self) -> None:
        """Wakes the poll loop so it reads the devices again.

        The event only signals; the loop owns the actual reading, so a refresh
        requested while a poll is running simply runs one more poll after it.
        """
        self._wake.set()

    def run(self) -> None:
        """Starts the window, the tray icon and the polling thread."""
        guard = singleton.acquire()
        if guard is None:
            return

        # The window owns the tkinter main loop, so it has to run on the main
        # thread. The tray icon runs detached in its own thread.
        from .window import BatteryWindow

        self._window = BatteryWindow(self)
        if self.show_window_on_start:
            self._window.deiconify()
        else:
            self._window.withdraw()
        self._window.protocol("WM_DELETE_WINDOW", self._window.withdraw)

        self._save_notification_icon()

        threading.Thread(target=self._loop, daemon=True).start()

        try:
            self._window.mainloop()
        finally:
            self._stop.set()
            self._wake.set()
            with self._icon_lock:
                icons = list(self._icons.values())
                self._icons.clear()
            for icon in icons:
                try:
                    icon.stop()
                except Exception:
                    pass
            guard.release()

    def _show_window(self) -> None:
        """Brings the main window to the front."""
        window = self._window
        if window is None:
            return
        try:
            window.post(window.show)
        except Exception:
            pass

    def rename_device(self, original_name: str, new_name: str) -> None:
        """Stores a custom name for a device and refreshes the view.

        Runs on the tkinter thread. The cached readings are reused instead of
        polling the devices again, so the rename shows up immediately.
        """
        self.config.set_custom_name(original_name, new_name)
        try:
            self.config.save()
        except OSError:
            pass

        with self._lock:
            devices = list(self.devices)

        if not devices:
            # Nothing cached yet; let the poll loop fill the list.
            self.request_refresh()
            return

        for device in devices:
            device.name = self.config.display_name(device.original_name)

        with self._lock:
            self.devices = devices

        window = self._window
        if window is not None:
            try:
                window.set_devices(devices)
            except Exception:
                pass

        if self._icons:
            try:
                self._sync_tray_icons(devices)
            except Exception:
                pass

    def _toggle_panel(self) -> None:
        """Shows or hides the popup with the battery levels."""
        window = self._window
        if window is None:
            return
        try:
            window.post(window.toggle_panel)
        except Exception:
            pass

    def _open_settings(self) -> None:
        """Shows the settings window."""
        window = self._window
        if window is None:
            return
        try:
            window.post(window.open_settings)
        except Exception:
            pass

    def _quit(self) -> None:
        """Stops the app and removes the tray icons."""
        self._stop.set()
        self._wake.set()
        with self._icon_lock:
            icons = list(self._icons.values())
            self._icons.clear()
        for icon in icons:
            try:
                icon.stop()
            except Exception:
                pass
        window = self._window
        if window is not None:
            try:
                window.post(window.destroy)
            except Exception:
                pass


def main() -> None:
    """Entry point."""
    TrayApp().run()


if __name__ == "__main__":
    main()
