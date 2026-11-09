"""Application settings, stored as JSON under ``%APPDATA%``."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_DIR_NAME = "BatteryTray"

# The kinds of peripheral the app knows about.
DEFAULT_KINDS = ("mouse", "headset")
EXTRA_KINDS = ("controller", "keyboard")
ALL_KINDS = DEFAULT_KINDS + EXTRA_KINDS


def config_dir() -> Path:
    """Returns the per-user configuration directory."""
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / APP_DIR_NAME


@dataclass
class Config:
    """User settings."""

    # Seconds between battery polls. The Razer dongle needs a moment to wake
    # up, so the default is deliberately lazy.
    poll_interval: int = 60
    # Also report peripherals that are neither a mouse nor a headset (game
    # controllers, keyboards). Kept for config files written before the
    # settings window existed.
    include_other_peripherals: bool = False
    # The kinds of peripheral the user wants to see. ``None`` means the
    # setting was never touched, so the defaults apply; an empty list means
    # the user switched every kind off.
    enabled_kinds: list[str] | None = None
    # Draw one battery per device instead of only the device with the lowest
    # charge.
    show_every_device: bool = True
    # Warn once when a device drops to this level.
    low_battery_threshold: int = 20
    # Notify when a device crosses the threshold.
    notify_low_battery: bool = True
    # Start with Windows.
    autostart: bool = False
    # Explicit whitelist of device names. Empty means "auto-detect".
    devices: list[str] = field(default_factory=list)
    # Custom names per device, keyed by the original device name.
    custom_names: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls) -> "Config":
        """Reads the config file, falling back to defaults."""
        path = config_dir() / "config.json"
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self) -> None:
        """Writes the config file, creating the directory when needed."""
        directory = config_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "config.json"
        path.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @property
    def poll_interval_seconds(self) -> int:
        """Poll interval clamped to a sane range."""
        return max(15, min(3600, self.poll_interval))

    @property
    def kinds(self) -> tuple[str, ...]:
        """The kinds of peripheral the user wants to see.

        A config file written before the setting existed has no entry, so it
        falls back to the default kinds.
        """
        if self.enabled_kinds is None:
            if self.include_other_peripherals:
                return ALL_KINDS
            return DEFAULT_KINDS
        return tuple(self.enabled_kinds)

    def set_enabled_kinds(self, kinds: list[str]) -> None:
        """Stores the kinds the user wants to see."""
        wanted = [k for k in kinds if k in ALL_KINDS]
        self.enabled_kinds = wanted
        # The old switch stays in sync so an old config file still behaves.
        self.include_other_peripherals = any(
            k not in DEFAULT_KINDS for k in wanted)

    def display_name(self, name: str) -> str:
        """The name shown for a device, honouring a custom one."""
        custom = self.custom_names.get(name, "").strip()
        return custom or name

    def set_custom_name(self, name: str, custom: str) -> None:
        """Sets or clears the custom name of a device.

        An empty custom name restores the original one.
        """
        if custom.strip():
            self.custom_names[name] = custom.strip()
        else:
            self.custom_names.pop(name, None)
