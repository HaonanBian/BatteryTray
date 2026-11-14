"""Pictures for the two places the battery is shown.

The main window shows one very large battery per device: a dark rounded
body, a coloured glass-like charge and a white contact on the right. The
tray popup shows a row of small line icons instead. Tkinter cannot draw a
soft gradient or an antialiased rounded corner, so those pictures are
painted with Pillow and then placed on a canvas.

The module only returns images; the text is drawn by the caller so it
stays crisp at every DPI.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from .dpi import scale_pixels

# The colours of the glass charge. They are muted on purpose, so the white
# number stays the brightest thing in the card.
CHARGE_HIGH = ((99, 131, 115), (92, 119, 107))
CHARGE_MEDIUM = ((157, 128, 87), (118, 94, 62))
CHARGE_LOW = ((154, 94, 100), (113, 67, 73))
CHARGE_CHARGING = ((91, 132, 153), (63, 98, 117))
CHARGE_NONE = None

# The body of the battery and the line around it.
CARD_TOP = (41, 48, 54)
CARD_BOTTOM = (36, 43, 49)
CARD_BORDER = (74, 82, 88)
CARD_BORDER_HOVER = (92, 100, 106)
CARD_GLOW = (112, 151, 127)

# The number is set in Segoe UI Variable, the font Windows 11 uses for its
# own interface. The variable file allows the light display cut to be used.
_FONT_PATHS = (
    Path("C:/Windows/Fonts/SegUIVar.ttf"),
    Path("C:/Windows/Fonts/segoeuil.ttf"),
    Path("C:/Windows/Fonts/segoeui.ttf"),
)


def _number_font(size: int, weight: int = 350) -> ImageFont.FreeTypeFont:
    """Loads the display face used for the big number."""
    for path in _FONT_PATHS:
        try:
            font = ImageFont.truetype(str(path), size)
        except (OSError, ValueError):
            continue
        if path.name.lower() == "seguivar.ttf":
            try:
                font.set_variation_by_axes([weight, 36])
            except (OSError, ValueError):
                try:
                    font.set_variation_by_name("Light Display")
                except (OSError, ValueError):
                    pass
        return font
    return ImageFont.load_default(size)


def charge_colors(percent: int | None, charging: bool = False):
    """The two ends of the gradient inside the battery."""
    if percent is None:
        return CHARGE_NONE
    if charging:
        return CHARGE_CHARGING
    if percent >= 60:
        return CHARGE_HIGH
    if percent >= 20:
        return CHARGE_MEDIUM
    return CHARGE_LOW


def _vertical_gradient(size: tuple[int, int], top: tuple[int, int, int],
                       bottom: tuple[int, int, int]) -> Image.Image:
    """A smooth vertical gradient, made without a loop over every pixel."""
    width, height = size
    if width < 1 or height < 1:
        return Image.new("RGBA", (1, 1), (*top, 255))
    column = Image.new("RGB", (1, height))
    draw = ImageDraw.Draw(column)
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = tuple(round(top[i] + (bottom[i] - top[i]) * ratio)
                      for i in range(3))
        draw.point((0, y), fill=color)
    return column.resize((width, height), Image.Resampling.BILINEAR).convert("RGBA")


def _rounded_mask(size: tuple[int, int], radius: float) -> Image.Image:
    """A white rounded rectangle on a transparent mask."""
    width, height = size
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, width - 1, height - 1), radius=max(0, radius), fill=255)
    return mask


def _paint_fill(size: tuple[int, int], colors, radius: float) -> Image.Image:
    """Paints the glass charge, including its grain and its soft top light."""
    width, height = max(1, size[0]), max(1, size[1])
    top, bottom = colors
    fill = _vertical_gradient((width, height), top, bottom)

    # A gentle grain keeps the large flat area from looking like plastic.
    noise = Image.effect_noise((width, height), 7).convert("L")
    noise = ImageChops.multiply(noise, Image.new("L", (width, height), 12))
    noise_layer = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    noise_layer.putalpha(noise)
    fill = Image.alpha_composite(fill, noise_layer)

    # The light that falls in from the top left corner.
    sheen = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sheen)
    draw.ellipse((-width * 0.35, -height * 0.9, width * 0.9, height * 0.45),
                 fill=(255, 255, 255, 8))
    sheen = sheen.filter(ImageFilter.GaussianBlur(max(2, height * 0.08)))
    fill = Image.alpha_composite(fill, sheen)
    fill.putalpha(_rounded_mask((width, height), radius))
    return fill


def render_battery(width: int, height: int, percent: int | None,
                   charging: bool = False, hover: bool = False,
                   dpi: float = 96.0, supersample: int = 3,
                   show_number: bool = True) -> Image.Image:
    """Paints a large horizontal battery.

    ``width`` and ``height`` are the size of the battery body in pixels.
    The white contact on the right is part of the picture as well: the
    caller gets an image that is a little wider than the body.
    """
    width = max(40, int(width))
    height = max(30, int(height))
    scale = max(1, int(supersample))
    w, h = width * scale, height * scale

    # The body ends before the contact, with a small gap in between. The
    # contact is about the height of a third of the body, just like the
    # battery icon of a phone.
    nub_w = max(scale * scale_pixels(8, dpi), round(h * 0.082))
    gap = max(scale * scale_pixels(7, dpi), round(h * 0.065))
    body_w = max(scale * 30, w - nub_w - gap)
    radius = max(scale * 2, h * 0.10)
    border = max(1, round(scale * 1.35 * dpi / 96.0))
    inset = max(scale * scale_pixels(12, dpi), round(h * 0.115))

    image = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    # ---- The glow behind the contact ----
    # A white pill with a little green light around it makes the contact
    # belong to the charge rather than look like a separate sticker.
    contact_h = round(h * 0.30)
    contact_top = (h - contact_h) // 2
    contact_left = body_w + gap
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.rounded_rectangle(
        (contact_left, contact_top, contact_left + nub_w,
         contact_top + contact_h),
        radius=nub_w / 2, fill=(174, 213, 185, 135))
    glow = glow.filter(ImageFilter.GaussianBlur(max(2, h * 0.045)))
    image = Image.alpha_composite(image, glow)

    # ---- The body ----
    body = _vertical_gradient(
        (body_w, h),
        tuple(min(255, c + 4) for c in CARD_TOP) if hover else CARD_TOP,
        tuple(min(255, c + 4) for c in CARD_BOTTOM) if hover else CARD_BOTTOM,
    )
    body.putalpha(_rounded_mask((body_w, h), radius))
    image.alpha_composite(body, (0, 0))

    # The charge is inset from the edge of the body; the part that is not
    # full stays the dark colour of the body.
    colors = charge_colors(percent, charging)
    if colors is not None and percent is not None and percent > 0:
        inner_w = body_w - 2 * inset
        inner_h = h - 2 * inset
        if inner_w > 2 and inner_h > 2:
            filled = max(1, round(inner_w * min(100, max(0, percent)) / 100))
            size = (max(1, filled), inner_h)
            fill_radius = min(inner_h / 2, h * 0.11, max(1, filled / 2))
            fill = _paint_fill(size, colors, fill_radius)
            fill.putalpha(_rounded_mask(size, fill_radius))
            image.alpha_composite(fill, (inset, inset))

            # A hairline along the top of the charge gives it a glass edge.
            line = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(line)
            draw.rounded_rectangle(
                (inset, inset, inset + filled - 1, inset + inner_h - 1),
                radius=fill_radius,
                outline=(255, 255, 255, 32),
                width=max(1, round(scale * dpi / 192)))
            image = Image.alpha_composite(image, line)

    # ---- The line around the body ----
    outline = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(outline)
    border_color = CARD_BORDER_HOVER if hover else CARD_BORDER
    draw.rounded_rectangle(
        (border / 2, border / 2, body_w - border / 2, h - border / 2),
        radius=radius,
        outline=(*border_color, 255),
        width=border)
    image = Image.alpha_composite(image, outline)

    # ---- The contact ----
    contact = _vertical_gradient(
        (nub_w, contact_h), (255, 255, 255), (238, 245, 239))
    contact.putalpha(_rounded_mask((nub_w, contact_h), nub_w / 2))
    image.alpha_composite(contact, (contact_left, contact_top))

    # ---- The number ----
    if show_number:
        text = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(text)
        baseline = int(h * 0.735)
        if percent is None:
            font = _number_font(max(1, int(h * 0.46)))
            label = "--"
            number_w = draw.textlength(label, font=font)
            draw.text(((body_w - number_w) / 2, baseline - h * 0.04),
                      label, font=font, fill=(232, 238, 233, 255), anchor="ls")
        else:
            number = str(percent)
            number_font = _number_font(max(1, int(h * 0.70)), weight=350)
            sign_font = _number_font(max(1, int(h * 0.40)), weight=350)
            widths = [draw.textlength(char, font=number_font) for char in number]
            sign_w = draw.textlength("%", font=sign_font)
            # The digits of the reference have generous air between them.
            digit_gap = h * 0.055
            sign_gap = h * 0.085
            total = sum(widths) + digit_gap * max(0, len(number) - 1) \
                + sign_gap + sign_w
            left = (body_w - total) / 2
            for char, char_width in zip(number, widths):
                draw.text((left, baseline), char, font=number_font,
                          fill=(250, 252, 250, 255), anchor="ls")
                left += char_width + digit_gap
            draw.text((left - digit_gap + sign_gap, baseline), "%",
                      font=sign_font, fill=(246, 249, 247, 255), anchor="ls")

        box = text.getbbox()
        if box is not None:
            painted = text.crop(box)
            text_x = (body_w - painted.width) / 2
            image.alpha_composite(painted, (round(text_x), box[1]))

    if scale != 1:
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    return image


# ---------------------------------------------------------------------------
# The small line icons of the tray popup
# ---------------------------------------------------------------------------

ICON_COLOR = (196, 203, 210, 255)


def _icon_canvas(size: int, scale: int = 4) -> tuple[Image.Image, ImageDraw.ImageDraw, int]:
    image = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    return image, ImageDraw.Draw(image), scale


def _stroke(scale: int, dpi: float) -> int:
    """The width of the lines of an icon."""
    return max(1, round(scale * 1.55 * dpi / 96.0))


def _draw_mouse(draw, size: int, scale: int, width: int, color) -> None:
    s = size * scale
    # A little taller than the squat version: about 45% more height while
    # keeping the same width.
    draw.rounded_rectangle(
        (s * 0.22, s * 0.08, s * 0.78, s * 0.86),
        radius=s * 0.23, outline=color, width=width)
    draw.line((s * 0.50, s * 0.11, s * 0.50, s * 0.40),
              fill=color, width=width)


def _draw_keyboard(draw, size: int, scale: int, width: int, color) -> None:
    s = size * scale
    draw.rounded_rectangle(
        (s * 0.08, s * 0.27, s * 0.92, s * 0.73),
        radius=s * 0.08, outline=color, width=width)
    for x in (0.30, 0.50, 0.70):
        draw.line((s * x, s * 0.38, s * x, s * 0.50),
                  fill=color, width=width)
    draw.line((s * 0.26, s * 0.61, s * 0.74, s * 0.61),
              fill=color, width=width)


def _draw_headset(draw, size: int, scale: int, width: int, color) -> None:
    s = size * scale
    draw.arc((s * 0.16, s * 0.10, s * 0.84, s * 0.76),
             start=185, end=355, fill=color, width=width)
    draw.rounded_rectangle(
        (s * 0.10, s * 0.43, s * 0.26, s * 0.84),
        radius=s * 0.07, outline=color, width=width)
    draw.rounded_rectangle(
        (s * 0.74, s * 0.43, s * 0.90, s * 0.84),
        radius=s * 0.07, outline=color, width=width)


def _draw_controller(draw, size: int, scale: int, width: int, color) -> None:
    s = size * scale
    draw.rounded_rectangle(
        (s * 0.08, s * 0.34, s * 0.92, s * 0.72),
        radius=s * 0.18, outline=color, width=width)
    draw.line((s * 0.28, s * 0.47, s * 0.28, s * 0.60),
              fill=color, width=width)
    draw.line((s * 0.21, s * 0.535, s * 0.35, s * 0.535),
              fill=color, width=width)
    draw.ellipse((s * 0.64, s * 0.44, s * 0.72, s * 0.52),
                 outline=color, width=width)
    draw.ellipse((s * 0.75, s * 0.54, s * 0.83, s * 0.62),
                 outline=color, width=width)


def _draw_device(draw, size: int, scale: int, width: int, color) -> None:
    s = size * scale
    draw.rounded_rectangle(
        (s * 0.18, s * 0.24, s * 0.82, s * 0.76),
        radius=s * 0.10, outline=color, width=width)
    draw.line((s * 0.36, s * 0.64, s * 0.64, s * 0.64),
              fill=color, width=width)


_ICON_PAINTERS = {
    "mouse": _draw_mouse,
    "keyboard": _draw_keyboard,
    "headset": _draw_headset,
    "controller": _draw_controller,
    "device": _draw_device,
}


def render_kind_icon(kind: str, size: int, dpi: float = 96.0,
                     color: tuple[int, int, int] = (196, 203, 210),
                     supersample: int = 4) -> Image.Image:
    """Draws the line icon of a device kind."""
    size = max(8, int(size))
    image, draw, scale = _icon_canvas(size, supersample)
    painter = _ICON_PAINTERS.get(kind, _draw_device)
    painter(draw, size, scale, _stroke(scale, dpi), (*color, 255))
    return image.resize((size, size), Image.Resampling.LANCZOS)


@lru_cache(maxsize=24)
def _cached_battery(width: int, height: int, percent: int | None,
                    charging: bool, hover: bool, dpi: float,
                    show_number: bool) -> Image.Image:
    return render_battery(width, height, percent, charging, hover, dpi,
                          show_number=show_number)


def battery_image(width: int, height: int, percent: int | None,
                  charging: bool = False, hover: bool = False,
                  dpi: float = 96.0, show_number: bool = True) -> Image.Image:
    """Returns a cached battery picture."""
    return _cached_battery(int(width), int(height), percent, bool(charging),
                           bool(hover), float(dpi), bool(show_number))


@lru_cache(maxsize=32)
def _cached_battery_icon(width: int, height: int, percent: int | None,
                         charging: bool, hover: bool,
                         text: str) -> Image.Image:
    """Paints the small battery that carries the percentage inside it."""
    width = max(16, int(width))
    height = max(10, int(height))
    scale = 4
    w, h = width * scale, height * scale

    nub_w = max(scale, round(h * 0.16))
    gap = max(scale, round(h * 0.06))
    body_w = max(scale * 6, w - nub_w - gap)
    radius = h * 0.28
    border = max(1, round(h * 0.045))
    inset = max(scale, round(h * 0.10))

    image = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    # The dark body of the battery.
    body = _vertical_gradient(
        (body_w, h),
        tuple(min(255, c + 4) for c in CARD_TOP) if hover else CARD_TOP,
        tuple(min(255, c + 4) for c in CARD_BOTTOM) if hover else CARD_BOTTOM,
    )
    body.putalpha(_rounded_mask((body_w, h), radius))
    image.alpha_composite(body, (0, 0))

    # The charge.
    colors = charge_colors(percent, charging)
    if colors is not None and percent is not None and percent > 0:
        inner_w = body_w - 2 * inset
        inner_h = h - 2 * inset
        if inner_w > 2 and inner_h > 2:
            filled = max(1, round(inner_w * min(100, max(0, percent)) / 100))
            fill_radius = min(inner_h / 2, h * 0.17, filled / 2)
            fill = _vertical_gradient((filled, inner_h), *colors)
            fill.putalpha(_rounded_mask((filled, inner_h), fill_radius))
            image.alpha_composite(fill, (inset, inset))

    # The line around the body.
    border_color = CARD_BORDER_HOVER if hover else CARD_BORDER
    outline = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(outline)
    draw.rounded_rectangle(
        (border / 2, border / 2, body_w - border / 2, h - border / 2),
        radius=radius, outline=(*border_color, 255), width=border)
    image = Image.alpha_composite(image, outline)

    # The white contact on the right.
    contact_h = round(h * 0.34)
    contact_top = (h - contact_h) // 2
    contact = Image.new("RGBA", (nub_w, contact_h), (0, 0, 0, 0))
    contact_draw = ImageDraw.Draw(contact)
    contact_draw.rounded_rectangle(
        (0, 0, nub_w - 1, contact_h - 1), radius=nub_w / 2,
        fill=(250, 252, 250, 255))
    image.alpha_composite(contact, (body_w + gap, contact_top))

    # The number sits inside the body, never on the contact.
    if text:
        draw = ImageDraw.Draw(image)
        font_px = max(scale * 5, int(h * 0.56))
        while font_px > scale * 4:
            font = _number_font(font_px, weight=380)
            box = draw.textbbox((0, 0), text, font=font, anchor="mm")
            if box[2] - box[0] <= body_w * 0.86:
                break
            font_px -= scale
        else:
            font = _number_font(max(scale * 4, font_px), weight=380)
        color = (250, 252, 250, 255) if percent is not None \
            else (182, 190, 197, 255)
        draw.text((body_w / 2, h / 2 - scale), text, font=font,
                  fill=color, anchor="mm")

    if scale != 1:
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    return image


def battery_icon_image(width: int, height: int, percent: int | None,
                       charging: bool = False, hover: bool = False,
                       text: str = "") -> Image.Image:
    """Returns a cached small battery icon, optionally with its number."""
    return _cached_battery_icon(int(width), int(height), percent,
                                bool(charging), bool(hover), str(text))


@lru_cache(maxsize=64)
def _cached_number(text: str, size: int, weight: int,
                   color: tuple[int, int, int]) -> Image.Image:
    scale = 3
    font = _number_font(max(1, int(size * scale)), weight)
    layer = Image.new("RGBA", (max(1, len(text)) * size * scale * 2,
                               size * scale * 3), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.text((0, 0), text, font=font, fill=(*color, 255), anchor="la")
    box = layer.getbbox()
    if box is None:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    layer = layer.crop(box)
    return layer.resize((max(1, layer.width // scale),
                         max(1, layer.height // scale)),
                        Image.Resampling.LANCZOS)


def number_image(text: str, size: int, weight: int = 300,
                 color: tuple[int, int, int] = (242, 245, 243)) -> Image.Image:
    """Paints a number with grayscale antialiasing for the tray strip."""
    return _cached_number(str(text), int(size), int(weight), tuple(color))
