#!/usr/bin/env python3
"""Measure panel geometry off the photo instead of eyeballing it.

The render is high contrast: pads, buttons and LEDs are saturated colour on a
near-grey chassis. Scanning a line across a row of controls and picking out the
runs of saturated pixels gives exact edges, which beats reading coordinates off
a screenshot by hand.

Prints layout.py-ready numbers.
"""

from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parent / "assets"
IMAGE = ASSETS / "atomsq_topdown.png"


def load():
    return Image.open(IMAGE).convert("RGB")


def saturation(pixel):
    r, g, b = pixel
    high, low = max(r, g, b), min(r, g, b)
    return 0 if high == 0 else (high - low) / high


def runs(values, threshold=0.28, min_len=12):
    """Contiguous stretches where value >= threshold."""
    out, start = [], None
    for index, value in enumerate(values):
        if value >= threshold:
            if start is None:
                start = index
        elif start is not None:
            if index - start >= min_len:
                out.append((start, index - 1))
            start = None
    if start is not None and len(values) - start >= min_len:
        out.append((start, len(values) - 1))
    return out


def scan_row(image, y, x0=0, x1=None, **kw):
    x1 = x1 if x1 is not None else image.width
    values = [saturation(image.getpixel((x, y))) for x in range(x0, x1)]
    return [(a + x0, b + x0) for a, b in runs(values, **kw)]


def scan_col(image, x, y0=0, y1=None, **kw):
    y1 = y1 if y1 is not None else image.height
    values = [saturation(image.getpixel((x, y))) for y in range(y0, y1)]
    return [(a + y0, b + y0) for a, b in runs(values, **kw)]


def summarise(name, spans):
    if not spans:
        print(f"{name}: nothing found")
        return None
    widths = [b - a + 1 for a, b in spans]
    starts = [a for a, _b in spans]
    pitches = [starts[i + 1] - starts[i] for i in range(len(starts) - 1)]
    print(f"{name}: {len(spans)} spans")
    print(f"  first start {starts[0]}, last start {starts[-1]}")
    print(f"  width  min {min(widths)} max {max(widths)} "
          f"mean {sum(widths) / len(widths):.1f}")
    if pitches:
        print(f"  pitch  min {min(pitches)} max {max(pitches)} "
              f"mean {sum(pitches) / len(pitches):.2f}")
    return spans


def main():
    image = load()
    print(f"{IMAGE.name}  {image.width} x {image.height}\n")

    # --- pads ---------------------------------------------------------
    # Lower row (numbered 1-16) and upper row, sampled through their middles.
    lower = summarise("pads lower row  (y=860)",
                      scan_row(image, 860, x0=100, min_len=40))
    upper = summarise("pads upper row  (y=690)",
                      scan_row(image, 690, x0=180, min_len=40))

    if lower:
        cx = (lower[3][0] + lower[3][1]) // 2
        vert = scan_col(image, cx, y0=600, min_len=40)
        print(f"  lower row vertical extent at x={cx}: {vert}")
    if upper:
        cx = (upper[3][0] + upper[3][1]) // 2
        vert = scan_col(image, cx, y0=560, y1=790, min_len=40)
        print(f"  upper row vertical extent at x={cx}: {vert}")
    print()

    # --- function pads (+/-) ------------------------------------------
    print("function pads column (x=140):",
          scan_col(image, 140, y0=560, y1=820, min_len=30))
    print("function pad + horizontal (y=660):",
          scan_row(image, 660, x0=40, x1=220, min_len=30))
    print()

    # --- touch strip LEDs ---------------------------------------------
    summarise("strip LEDs (y=436)", scan_row(image, 436, x0=400, x1=1500,
                                             min_len=6))
    led_spans = scan_row(image, 436, x0=400, x1=1500, min_len=6)
    if led_spans:
        cx = (led_spans[0][0] + led_spans[0][1]) // 2
        print("  LED vertical extent:",
              scan_col(image, cx, y0=410, y1=470, min_len=4))
    print()

    # --- screen --------------------------------------------------------
    # The render fills the LCD with a teal wash, so it segments cleanly.
    print("screen horizontal (y=270):",
          scan_row(image, 270, x0=1450, x1=2000, min_len=80))
    print("screen vertical  (x=1700):",
          scan_col(image, 1700, y0=80, y1=460, min_len=80))
    print()

    # --- button rows ---------------------------------------------------
    summarise("A-D row (y=387)", scan_row(image, 387, x0=20, x1=460,
                                          min_len=30))
    print("  A-D vertical (x=90):", scan_col(image, 90, y0=340, y1=470,
                                             min_len=15))
    summarise("E-H row (y=445)", scan_row(image, 445, x0=20, x1=460,
                                          min_len=30))
    summarise("transport row (y=545)", scan_row(image, 545, x0=20, x1=460,
                                                min_len=30))
    print("  transport vertical (x=95):", scan_col(image, 95, y0=490, y1=610,
                                                   min_len=30))
    print()

    print("mode column (x=1440):", scan_col(image, 1440, y0=90, y1=440,
                                            min_len=20))
    print("mode row (y=150):", scan_row(image, 150, x0=1380, x1=1520,
                                        min_len=20))
    print()

    print("soft buttons above screen (y=85):",
          scan_row(image, 85, x0=1500, x1=1900, min_len=20))
    print("  vertical (x=1610):", scan_col(image, 1610, y0=50, y1=120,
                                           min_len=10))
    print("soft buttons below screen (y=432):",
          scan_row(image, 432, x0=1500, x1=1900, min_len=20))
    print("  vertical (x=1610):", scan_col(image, 1610, y0=400, y1=470,
                                           min_len=10))
    print()

    print("nav up (x=1740 col):", scan_col(image, 1740, y0=460, y1=620,
                                           min_len=15))
    print("nav row (y=570):", scan_row(image, 570, x0=1500, x1=2100,
                                       min_len=20))
    print("wheel l/r (y=390):", scan_row(image, 390, x0=1900, x1=2140,
                                         min_len=20))
    print("wheel l/r vertical (x=1960):", scan_col(image, 1960, y0=360,
                                                   y1=430, min_len=10))
    print("shift (y=560):", scan_row(image, 560, x0=1950, x1=2140, min_len=20))
    print("shift vertical (x=2010):", scan_col(image, 2010, y0=520, y1=620,
                                               min_len=15))


if __name__ == "__main__":
    main()
