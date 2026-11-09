"""Tray icon rendering.

Draws the battery state as a compact lightning bolt that stays readable at the
16-24 px the Windows notification area uses. The bolt is coloured by the
battery level, so the icon still tells the user how much charge is left while
looking like a lightning mark.
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw

# Icon sizes the Windows notification area uses.
ICON_SIZES = (16, 20, 24, 32)

# Thresholds for the level colour.
COLOR_FULL = (46, 160, 67, 255)      # green, >= 60%
COLOR_MID = (219, 154, 26, 255)       # amber, 20-59%
COLOR_LOW = (211, 47, 47, 255)       # red, < 20%
COLOR_EMPTY = (117, 117, 117, 255)    # grey, unknown or offline
COLOR_CHARGING = (66, 133, 244, 255)  # blue, charging
COLOR_FRAME = (220, 220, 220, 255)    # outline

# The lightning bolt, in normalised coordinates with the origin in the top
# left corner and the y axis pointing down.
BOLT_SHAPE = (
    (0.60, 0.00),
    (0.18, 0.56),
    (0.44, 0.56),
    (0.38, 1.00),
    (0.82, 0.44),
    (0.56, 0.44),
)


@dataclass(frozen=True)
class DeviceState:
    """What the icon should show."""

    percent: int | None
    charging: bool = False
    connected: bool = True


def level_color(percent: int | None, charging: bool = False) -> tuple[int, int, int, int]:
    """Picks the fill colour for a battery level."""
    if percent is None:
        return COLOR_EMPTY
    if charging:
        return COLOR_CHARGING
    if percent >= 60:
        return COLOR_FULL
    if percent >= 20:
        return COLOR_MID
    return COLOR_LOW


def _bolt_points(left: float, top: float, width: float,
                 height: float) -> list[tuple[float, float]]:
    """Scales the bolt shape into the given box."""
    return [(left + x * width, top + y * height) for x, y in BOLT_SHAPE]


def _render_single(size: int, state: DeviceState) -> Image.Image:
    """Draws one lightning bolt."""
    scale = 4  # supersample for smooth edges
    dim = size * scale
    image = Image.new("RGBA", (dim, dim), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    margin = max(1, dim // 8)
    bolt_w = dim - margin * 2
    bolt_h = dim - margin * 2
    left = margin
    top = margin
    points = _bolt_points(left, top, bolt_w, bolt_h)

    color = level_color(state.percent, state.charging)

    # A dark halo keeps the bolt readable on a light taskbar.
    halo_w = max(1, dim // 24)
    draw.polygon(points, fill=(0, 0, 0, 200),
                 outline=(0, 0, 0, 200), width=halo_w * 2)

    draw.polygon(points, fill=color)

    return image.resize((size, size), Image.LANCZOS)


def _render_multi(size: int, states: list[DeviceState]) -> Image.Image:
    """Draws one small bolt per device, side by side."""
    scale = 4
    dim = size * scale
    image = Image.new("RGBA", (dim, dim), (0, 0, 0, 0))

    count = len(states)
    if count == 1:
        return _render_single(size, states[0])

    # Each bolt gets an equal slice of the width.
    slot = dim / count
    bolt_w = int(slot * 0.72)
    bolt_h = int(dim * 0.78)
    outline_w = max(1, dim // 28)

    for index, state in enumerate(states):
        center_x = int(slot * (index + 0.5))
        left = center_x - bolt_w // 2
        top = (dim - bolt_h) // 2
        points = _bolt_points(left, top, bolt_w, bolt_h)

        color = level_color(state.percent, state.charging)
        draw = ImageDraw.Draw(image)
        draw.polygon(points, fill=(0, 0, 0, 200),
                     outline=(0, 0, 0, 200), width=outline_w * 2)
        draw.polygon(points, fill=color)

    return image.resize((size, size), Image.LANCZOS)


def build_icon(states: list[DeviceState], size: int = 32) -> Image.Image:
    """Builds the tray icon for the given device states."""
    if not states:
        image = Image.new("RGBA", (size * 4, size * 4), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        dim = size * 4
        margin = max(1, dim // 8)
        draw.polygon(
            _bolt_points(margin, margin, dim - margin * 2, dim - margin * 2),
            fill=COLOR_EMPTY,
        )
        return image.resize((size, size), Image.LANCZOS)
    if len(states) == 1:
        return _render_single(size, states[0])
    return _render_multi(size, states)
