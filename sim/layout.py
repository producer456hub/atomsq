#!/usr/bin/env python3
"""Panel geometry for the ATOM SQ, in the coordinate space of the photo.

All rectangles are in pixels of `assets/atomsq_topdown.png` (2155 x 1032), the
official top-down render extracted from the owner's manual. The simulator
scales them with the image, so controls stay registered to the photo at any
window size.

These numbers are **measured, not eyeballed**: `measure.py` scans lines across
the render and picks out the runs of saturated pixels, which gives exact edges
for every pad, button and LED. Re-run it after changing the asset. Press `c` in
the simulator to see the outlines drawn over the artwork.
"""

from __future__ import annotations

IMAGE = "atomsq_topdown.png"
IMAGE_W, IMAGE_H = 2155, 1032


def rect(x, y, w, h):
    return (float(x), float(y), float(x + w), float(y + h))


def grid(x0, y0, w, h, pitch, count):
    """`count` rects marching right from (x0, y0)."""
    return [rect(x0 + i * pitch, y0, w, h) for i in range(count)]


# --------------------------------------------------------------------------
# Pads — two staggered rows of 16, like white/black keys.
#
# surface.xml calls the lower (numbered 1-16) row pad[0][*] = notes 0x24-0x33,
# and the upper row pad[1][*] = 0x34-0x43. Measured pitch is the same on both
# rows (116.5 px); the upper row sits 59 px right, almost exactly half a pitch,
# which is what makes the layout "staggered".
# --------------------------------------------------------------------------

PAD_PITCH = 116.53
PAD_W, PAD_H = 88.0, 148.0

PADS_LOWER = grid(160.0, 805.0, PAD_W, PAD_H, PAD_PITCH, 16)   # pad[0][*]
PADS_UPPER = grid(219.0, 630.0, PAD_W, PAD_H, PAD_PITCH, 16)   # pad[1][*]

# Index 0..31 in note order: note 0x24 is the first pad of the lower row.
PADS = PADS_LOWER + PADS_UPPER

# The two function pads left of the grid — notes 0x00 (+) and 0x01 (-).
FUNCTION_PADS = {
    "plus": rect(98.0, 629.0, 85.0, 56.0),
    "minus": rect(98.0, 718.0, 85.0, 56.0),
}

# --------------------------------------------------------------------------
# Screen — 14 text cells laid out 3 columns above / 2 wide lines / 3 columns
# below, exactly as Studio One's own device panel draws it. Confirmed on
# hardware: writing cell ids 0..D lands where this table says it should.
# --------------------------------------------------------------------------

SCREEN = rect(1571.0, 149.0, 292.0, 221.0)

# --------------------------------------------------------------------------
# Knobs — 8 endless encoders (CC 0x0E-0x15) and the big wheel (CC 0x1D).
# Stored as (cx, cy, radius). Knobs are dark on dark, so these come from
# visual alignment against the render rather than the saturation scan.
# --------------------------------------------------------------------------

KNOBS = [
    (643.3, 150.9, 77.6), (858.8, 150.9, 77.6),
    (1073.2, 150.9, 77.6), (1288.7, 150.9, 77.6),
    (538.8, 321.1, 75.4), (754.3, 321.1, 75.4),
    (967.6, 321.1, 75.4), (1182.0, 321.1, 75.4),
]
WHEEL = (2012.8, 282.3, 84.0)

# --------------------------------------------------------------------------
# Touch strip — 25 LEDs above the ribbon, CC 55-79. Measured pitch 37.5 px.
# --------------------------------------------------------------------------

STRIP_BODY = rect(461.0, 457.0, 1024.0, 133.0)
STRIP_LEDS = grid(515.0, 436.0, 14.0, 14.0, 37.5, 25)

# --------------------------------------------------------------------------
# Buttons, keyed by the names used in probe/atomsq.py BUTTONS.
# --------------------------------------------------------------------------

# The four left-hand columns are shared by A-D, E-H and the transport row.
_COL_X = [52.0, 149.0, 245.0, 341.0]
_AH_W, _AH_H = 76.0, 33.0

_TRANSPORT_X = [55.0, 152.0, 246.0, 341.0]

# Screen soft buttons: three above, three below, same columns.
_LCD_X = [1585.0, 1684.0, 1782.0]
_LCD_W = 72.0

BUTTONS = {
    # Function buttons A-H, two rows of four.
    "A": rect(_COL_X[0], 376.0, _AH_W, _AH_H),
    "B": rect(_COL_X[1], 376.0, _AH_W, _AH_H),
    "C": rect(_COL_X[2], 376.0, _AH_W, _AH_H),
    "D": rect(_COL_X[3], 376.0, _AH_W, _AH_H),
    "E": rect(_COL_X[0], 434.0, _AH_W, _AH_H),
    "F": rect(_COL_X[1], 434.0, _AH_W, _AH_H),
    "G": rect(_COL_X[2], 434.0, _AH_W, _AH_H),
    "H": rect(_COL_X[3], 434.0, _AH_W, _AH_H),

    # Transport. The printed labels (Undo/Loop/Save/Count In) are the shifted
    # functions; unshifted these are stop/play/record/metronome.
    "stop": rect(_TRANSPORT_X[0], 511.0, 72.0, 71.0),
    "play": rect(_TRANSPORT_X[1], 511.0, 76.0, 71.0),
    "record": rect(_TRANSPORT_X[2], 511.0, 72.0, 71.0),
    "metronome": rect(_TRANSPORT_X[3], 511.0, 76.0, 71.0),

    # Mode column, left of the screen.
    "song": rect(1411.0, 127.0, 72.0, 49.0),
    "inst": rect(1411.0, 203.0, 72.0, 49.0),
    "editor": rect(1411.0, 280.0, 72.0, 49.0),
    "user": rect(1411.0, 357.0, 72.0, 49.0),

    "lcd1": rect(_LCD_X[0], 74.0, _LCD_W, 29.0),
    "lcd2": rect(_LCD_X[1], 74.0, _LCD_W, 29.0),
    "lcd3": rect(_LCD_X[2], 74.0, _LCD_W, 29.0),
    "lcd4": rect(_LCD_X[0], 419.0, _LCD_W, 31.0),
    "lcd5": rect(_LCD_X[1], 419.0, _LCD_W, 31.0),
    "lcd6": rect(_LCD_X[2], 419.0, _LCD_W, 31.0),

    # Left/right either side of the big wheel.
    "wheel_left": rect(1935.0, 370.0, 56.0, 29.0),
    "wheel_right": rect(2017.0, 370.0, 64.0, 29.0),

    # Navigation cluster: up alone, then left/down/right in a row.
    "up": rect(_LCD_X[1], 493.0, _LCD_W, 30.0),
    "left": rect(_LCD_X[0], 552.0, _LCD_W, 30.0),
    "down": rect(_LCD_X[1], 552.0, _LCD_W, 30.0),
    "right": rect(_LCD_X[2], 552.0, _LCD_W, 30.0),

    "shift": rect(1978.0, 535.0, 71.0, 46.0),
}

# On the panel but not addressable — drawn only so hit regions are complete.
SETUP_BUTTON = (2006.3, 88.4, 23.7)
