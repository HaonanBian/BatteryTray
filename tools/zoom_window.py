"""Zooms into a part of the rendered window.

    python tools/zoom_window.py 0 0 912 779
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

IMAGE = Path(__file__).resolve().parent.parent / "_window.png"
OUT = Path(__file__).resolve().parent.parent / "_zoom.png"


def main() -> None:
    """Crops the window and saves a bigger picture of it."""
    image = Image.open(IMAGE).convert("RGB")
    args = [int(a) for a in sys.argv[1:]]
    if len(args) == 4:
        box = tuple(args)
    else:
        box = (0, 0, image.width, image.height)
    crop = image.crop(box)
    scale = max(1, 1400 // max(1, crop.width))
    crop = crop.resize((crop.width * scale, crop.height * scale),
                       Image.LANCZOS)
    crop.save(OUT)
    print("saved", OUT, crop.size)


if __name__ == "__main__":
    main()
