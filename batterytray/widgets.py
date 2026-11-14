"""Custom widgets for the dark look.

Tkinter has no rounded corners, no soft shadows and no custom shaped
gauges, so the parts of the interface that need them are drawn on a
canvas. This module holds those drawings:

* the colour palette of the dark theme,
* :func:`rounded_points`, which builds the outline of a rounded
  rectangle,
* :func:`draw_rounded_rect`, which paints such a rectangle on a canvas,
* :func:`draw_battery`, which paints the classic battery: a rounded
  body with a small contact on the right side and the charge as a
  coloured fill,
* :func:`draw_charge_bar`, a slim version of the same thing,
* :class:`GlassButton`, a flat button with rounded corners that reacts
  to the pointer.

Everything is drawn with plain polygons and a text, so no picture
library is needed and the drawing stays sharp at every size.
"""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import font as tkfont

from .dpi import scale_pixels

# ---------------------------------------------------------------------------
# The palette of the dark glass theme
# ---------------------------------------------------------------------------

# The colour of the window itself.
BG = "#20252C"
# The colour of a card that sits on the window.
BG_CARD = "#272E35"
# The colour of a card while the pointer is over it.
BG_CARD_HOVER = "#2C343C"
# A very faint line that separates a card from the window.
BG_BORDER = "#3A424A"
# The colour of an input field.
BG_FIELD = "#161B20"
# The colour of a divider line.
BG_DIVIDER = "#333B43"
# The colour of a small chip, such as the one that names the device kind.
BG_CHIP = "#2C343C"
# The colour of a chip while the pointer is over the card.
BG_CHIP_HOVER = "#343D46"

FG = "#F2F5F7"
FG_DIM = "#A9B3BC"
FG_MUTED = "#7E8993"

# The green used for a healthy battery and for the accent of the app.
ACCENT = "#A9D3B6"
# The colour of a battery that is charging.
CHARGING = "#8FC3DF"
WARNING = "#D8BB83"
DANGER = "#DE9BA2"

# The colour of the outline of a battery.
BATTERY_OUTLINE = "#4C555E"
# The colour of the contact on the right side of a battery.
BATTERY_CONTACT = "#454E57"
# The colour inside of an empty battery.
BATTERY_EMPTY = "#1B2127"

# The levels at which the colour of the battery changes.
HIGH = 60
MEDIUM = 20


def level_color(percent: int | None, charging: bool = False) -> str:
    """Colour for a battery level."""
    if percent is None:
        return FG_MUTED
    if charging:
        return CHARGING
    if percent >= HIGH:
        return ACCENT
    if percent >= MEDIUM:
        return WARNING
    return DANGER


def _readable_on(color: str) -> str:
    """Picks the colour of text that is put on top of ``color``.

    A bright colour wants dark text, a dark one wants light text.
    """
    value = color.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    red, green, blue = (int(value[0:2], 16), int(value[2:4], 16),
                        int(value[4:6], 16))
    brightness = (red * 299 + green * 587 + blue * 114) / 1000
    return "#20252C" if brightness > 140 else FG


def rounded_points(x1: float, y1: float, x2: float, y2: float,
                   radius: float, steps: int = 8) -> list[float]:
    """The outline of a rounded rectangle as a flat list of coordinates.

    The corners are built from small arcs, so the shape can be drawn on a
    canvas as a plain polygon.
    """
    width = x2 - x1
    height = y2 - y1
    radius = max(0.0, min(radius, width / 2, height / 2))
    if radius <= 0:
        return [x1, y1, x2, y1, x2, y2, x1, y2]

    points: list[float] = []

    def arc(cx: float, cy: float, start: float, end: float) -> None:
        for step in range(steps + 1):
            angle = start + (end - start) * step / steps
            points.append(cx + radius * math.cos(angle))
            points.append(cy + radius * math.sin(angle))

    arc(x1 + radius, y1 + radius, math.pi, 1.5 * math.pi)
    arc(x2 - radius, y1 + radius, 1.5 * math.pi, 2.0 * math.pi)
    arc(x2 - radius, y2 - radius, 0.0, math.pi / 2)
    arc(x1 + radius, y2 - radius, math.pi / 2, math.pi)
    return points


def draw_rounded_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float,
                      y2: float, radius: float, fill: str,
                      outline: str = "", width: int = 1, tags=()) -> int:
    """Paints a rounded rectangle on a canvas and returns its id."""
    points = rounded_points(x1, y1, x2, y2, radius)
    return canvas.create_polygon(points, fill=fill, outline=outline,
                                 width=width, smooth=False, tags=tags)


def draw_battery(canvas: tk.Canvas, x: float, y: float, width: float,
                 height: float, percent: int | None,
                 charging: bool = False, text: str = "", font=None,
                 tags=()) -> float:
    """Paints a simple battery and returns the width of its body.

    The body is a rounded rectangle with a small contact on the right
    side. The charge is a plain coloured fill that grows from the left.
    The number of the charge can be printed in the middle of the body.

    The drawing is kept plain on purpose: the icon has to be readable
    at a small size, and a battery that tries to look like a piece of
    glass turns into noise once it is only a few points high.
    """
    contact_width = max(2.0, height * 0.14)
    gap = max(1.0, height * 0.08)
    body_width = width - contact_width - gap
    body_right = x + body_width
    radius = max(2.0, height * 0.28)
    stroke = max(1.0, height * 0.09)

    # The contact on the right side.
    contact = rounded_points(body_right + gap, y + height * 0.32,
                             x + width, y + height * 0.68,
                             max(1.0, contact_width / 2))
    canvas.create_polygon(contact, fill=BATTERY_CONTACT, outline="", tags=tags)

    # The body of the battery.
    body = rounded_points(x, y, body_right, y + height, radius)
    canvas.create_polygon(body, fill=BATTERY_EMPTY,
                          outline=BATTERY_OUTLINE, width=stroke, tags=tags)

    # The charge.
    color = level_color(percent, charging)
    filled = 0.0
    if percent is not None and percent > 0:
        inner_left = x + stroke
        inner_right = body_right - stroke
        inner_width = max(0.0, inner_right - inner_left)
        filled = inner_width * max(0, min(100, percent)) / 100
        if filled > 0:
            fill = rounded_points(inner_left, y + stroke,
                                  inner_left + filled, y + height - stroke,
                                  max(1.0, radius - stroke))
            canvas.create_polygon(fill, fill=color, outline="", tags=tags)
            # The right end of the fill is squared off, so the charge does
            # not look like a floating pill.
            right = min(inner_left + filled, inner_right)
            canvas.create_rectangle(right - radius, y + stroke, right,
                                    y + height - stroke, fill=color,
                                    outline="", tags=tags)

    # The number of the charge, printed in the body of the battery.
    if text:
        # The number sits on the charge when the charge reaches the
        # middle of the body. A dark number is then easier to read than
        # a light one, and the other way around.
        middle = x + body_width / 2
        on_fill = filled > 0 and middle < x + stroke + filled
        canvas.create_text(middle, y + height / 2, text=text,
                           fill=_readable_on(color) if on_fill else FG,
                           font=font, tags=tags)

    return body_width


def draw_charge_bar(canvas: tk.Canvas, x: float, y: float, width: float,
                    height: float, percent: int | None, charging: bool = False,
                    tags=()) -> float:
    """Paints a slim bar that shows the charge.

    This is the shape of the battery of a phone without the frame: a
    thin track with a coloured fill that grows from the left. It is
    used where there is no room for a whole battery.
    """
    radius = height / 2
    canvas.create_polygon(rounded_points(x, y, x + width, y + height, radius),
                          fill=BATTERY_EMPTY, outline="", tags=tags)
    if percent is None or percent <= 0:
        return width

    filled = width * max(0, min(100, percent)) / 100
    color = level_color(percent, charging)
    if filled <= 0:
        return width
    canvas.create_polygon(
        rounded_points(x, y, x + filled, y + height, radius),
        fill=color, outline="", tags=tags)
    return width


def draw_bolt(canvas: tk.Canvas, cx: float, cy: float, size: float,
              color: str, tags=()) -> None:
    """Paints the little bolt that marks a battery that is charging."""
    canvas.create_polygon(
        cx + size * 0.25, cy - size,
        cx - size * 0.35, cy + size * 0.1,
        cx - size * 0.02, cy + size * 0.1,
        cx - size * 0.3, cy + size,
        cx + size * 0.38, cy - size * 0.12,
        cx + size * 0.04, cy - size * 0.12,
        fill=color, outline="", tags=tags)


class GlassButton(tk.Canvas):
    """A flat button with rounded corners."""

    def __init__(self, master: tk.Misc, text: str, family: str, dpi: float,
                 command=None, accent: bool = False, background: str = BG):
        super().__init__(master, bg=background, highlightthickness=0, bd=0,
                         cursor="hand2")
        self.family = family
        self.dpi = dpi
        self._text = text
        self._command = command
        self._accent = accent
        self._hover = False
        self._pressed = False

        self._font = (family, -scale_pixels(11, dpi),
                      "bold" if accent else "normal")
        pad_x = scale_pixels(15, dpi)
        pad_y = scale_pixels(6, dpi)
        measure = tkfont.Font(root=self, font=self._font)
        self._width = measure.measure(text) + pad_x * 2
        self._height = measure.metrics("linespace") + pad_y * 2
        self.configure(width=self._width, height=self._height)

        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self._draw()

    # -- colours -------------------------------------------------------

    def _fill(self) -> str:
        """The colour of the button."""
        if self._accent:
            if self._pressed:
                return "#93BFA3"
            return "#BADFC7" if self._hover else "#A9D3B6"
        if self._pressed:
            return "#242A30"
        return "#333B43" if self._hover else "#2A3138"

    def _text_color(self) -> str:
        """The colour of the text on the button."""
        if self._accent:
            return "#142019"
        return FG if self._hover else FG_DIM

    def _draw(self) -> None:
        """Draws the button."""
        self.delete("all")
        shape = rounded_points(1, 1, self._width - 1, self._height - 1,
                               max(2, self._height * 0.32))
        self.create_polygon(shape, fill=self._fill(), outline="")
        self.create_text(self._width / 2, self._height / 2, text=self._text,
                         fill=self._text_color(), font=self._font)

    # -- events ---------------------------------------------------------

    def _on_press(self, _event=None) -> None:
        """The button is pushed in."""
        self._pressed = True
        self._draw()

    def _on_release(self, event) -> None:
        """The button is released; the command runs when it was a click."""
        was_pressed = self._pressed
        self._pressed = False
        self._draw()
        if not was_pressed:
            return
        # The click only counts when the pointer is still on the button.
        if not (0 <= event.x <= self._width and 0 <= event.y <= self._height):
            return
        if self._command is not None:
            self._command()

    def _on_enter(self, _event=None) -> None:
        """The pointer is over the button."""
        self._hover = True
        self._draw()

    def _on_leave(self, _event=None) -> None:
        """The pointer left the button."""
        self._hover = False
        self._pressed = False
        self._draw()
