"""Looks at the colours in the rendered panel.

    python tools/probe_panel.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

IMAGE = Path(__file__).resolve().parent.parent / "_panel.png"

# The colours the panel is made of.
ACCENT = (67, 217, 138)
CHARGING = (63, 182, 245)
WARNING = (242, 179, 61)
DANGER = (240, 97, 109)
TROUGH = (14, 16, 20)
CARD = (21, 23, 28)


def main() -> None:
    """Prints where the colours of the panel are."""
    image = Image.open(IMAGE).convert("RGB")
    width, height = image.size
    pixels = image.load()

    counter = Counter()
    for y in range(height):
        for x in range(width):
            counter[pixels[x, y]] += 1

    print("size:", image.size)
    for colour, count in counter.most_common(8):
        print("common", colour, count)

    for name, colour in (("accent", ACCENT), ("charging", CHARGING),
                         ("warning", WARNING), ("danger", DANGER),
                         ("trough", TROUGH)):
        spots = [(x, y) for y in range(height) for x in range(width)
                 if pixels[x, y] == colour]
        if not spots:
            print(name, colour, "not found")
            continue
        xs = [p[0] for p in spots]
        ys = [p[1] for p in spots]
        print(name, colour, "count", len(spots),
              "x", min(xs), max(xs), "y", min(ys), max(ys))


if __name__ == "__main__":
    main()
