"""Tray icon rendering.

Draws the battery state as a compact lightning bolt that stays readable at the
16-24 px the Windows notification area uses. The bolt is coloured by the
battery level, so the icon still tells the user how much charge is left while
looking like a lightning mark.
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw

from .art import render_kind_icon

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


# The ring follows the same colour scale as the rest of the app.
RING_TRACK = (63, 69, 77, 230)
RING_CHARGING = (72, 211, 128, 255)


def _solid_device(kind: str, size: int,
                  color: tuple[int, int, int] = (238, 242, 246)) -> Image.Image:
    """Draws a filled white device silhouette with transparent details.

    The reference icons are solid shapes rather than line drawings; the
    wheel, keys and buttons are holes through which the dark surround shows.
    """
    s = max(8, int(size))
    mask = Image.new("L", (s, s), 0)
    draw = ImageDraw.Draw(mask)
    sc = s / 100.0

    if kind == "mouse":
        draw.rounded_rectangle(
            (24 * sc, 4 * sc, 76 * sc, 95 * sc), radius=26 * sc, fill=255)
        # The two mouse buttons and the scroll wheel are cut-outs.
        draw.rectangle((20 * sc, 36 * sc, 80 * sc, 41 * sc), fill=0)
        draw.rectangle((49 * sc, 3 * sc, 51 * sc, 12 * sc), fill=0)
        draw.rounded_rectangle(
            (43 * sc, 12 * sc, 57 * sc, 31 * sc), radius=7 * sc, fill=0)
        draw.rectangle((49 * sc, 31 * sc, 51 * sc, 36 * sc), fill=0)
    elif kind == "keyboard":
        draw.rounded_rectangle(
            (6 * sc, 29 * sc, 94 * sc, 71 * sc), radius=10 * sc, fill=255)
        for x in (19, 31, 43, 55, 67):
            draw.rounded_rectangle(
                (x * sc, 38 * sc, (x + 6) * sc, 46 * sc),
                radius=2 * sc, fill=0)
        draw.rounded_rectangle(
            (19 * sc, 56 * sc, 81 * sc, 63 * sc), radius=2 * sc, fill=0)
    elif kind == "controller":
        draw.ellipse((10 * sc, 28 * sc, 90 * sc, 70 * sc), fill=255)
        draw.ellipse((1 * sc, 38 * sc, 36 * sc, 88 * sc), fill=255)
        draw.ellipse((64 * sc, 38 * sc, 99 * sc, 88 * sc), fill=255)
        draw.rectangle((18 * sc, 38 * sc, 82 * sc, 68 * sc), fill=255)
        # D-pad.
        draw.rectangle((20 * sc, 49 * sc, 35 * sc, 54 * sc), fill=0)
        draw.rectangle((25 * sc, 44 * sc, 30 * sc, 59 * sc), fill=0)
        # Four round face buttons.
        for cx, cy in ((66, 47), (75, 52), (66, 57), (57, 52)):
            draw.ellipse(
                ((cx - 2.5) * sc, (cy - 2.5) * sc,
                 (cx + 2.5) * sc, (cy + 2.5) * sc), fill=0)
    else:
        return render_kind_icon(kind, size, 96, color=color)

    glyph = Image.new("RGBA", (s, s), (*color, 255))
    glyph.putalpha(mask)
    return glyph


def build_device_icon(kind: str, percent: int | None,
                      charging: bool = False, connected: bool = True,
                      size: int = 64) -> Image.Image:
    """Draws a device icon inside a ring that shows its charge.

    The ring starts at the top and fills clockwise, using the same green,
    amber, red and blue as the rest of the app. A small green badge with a
    bolt marks a device that is charging.
    """
    size = max(16, int(size))
    scale = 4
    dim = size * scale
    image = Image.new("RGBA", (dim, dim), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    margin = int(dim * 0.055)
    ring = max(2, int(dim * 0.082))
    box = (margin, margin, dim - margin, dim - margin)
    draw.ellipse(box, outline=RING_TRACK, width=ring)

    color = level_color(percent, charging) if connected else COLOR_EMPTY
    if percent is not None and connected:
        filled = max(0, min(100, percent))
        if filled >= 99:
            draw.ellipse(box, outline=color, width=ring)
        elif filled > 0:
            end = -90 + 360 * filled / 100
            draw.arc(box, start=-90, end=end, fill=color, width=ring)

    icon_size = int(dim * 0.44)
    icon_color = (238, 242, 246) if connected else (150, 158, 165)
    if kind in ("mouse", "keyboard", "controller"):
        device = _solid_device(kind, icon_size, icon_color)
    else:
        device = render_kind_icon(kind, icon_size, 96, color=icon_color)
    image.alpha_composite(device, ((dim - icon_size) // 2,
                                   (dim - icon_size) // 2))

    if charging and connected:
        badge = int(dim * 0.26)
        left = dim - margin - badge
        top = dim - margin - badge
        draw.ellipse((left, top, left + badge, top + badge),
                     fill=RING_CHARGING)
        cx, cy = left + badge / 2, top + badge / 2
        r = badge * 0.26
        draw.polygon((
            cx + r * 0.35, cy - r,
            cx - r * 0.55, cy + r * 0.1,
            cx - r * 0.05, cy + r * 0.1,
            cx - r * 0.35, cy + r,
            cx + r * 0.55, cy - r * 0.1,
            cx + r * 0.05, cy - r * 0.1,
        ), fill=(20, 35, 25, 255))

    if scale != 1:
        image = image.resize((size, size), Image.Resampling.LANCZOS)
    return image
