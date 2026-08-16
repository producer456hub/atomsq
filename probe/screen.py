#!/usr/bin/env python3
"""Screen probe — settle the cell layout, colour and icon-font questions.

    python screen.py map      write each cell's own id into it (layout proof)
    python screen.py names    write the community-claimed cell NAMES into cells
    python screen.py icons    render all 16 private-font glyphs
    python screen.py colors   colour ramp across cells
    python screen.py align    left/center/right in every cell
    python screen.py len      find the real max text length per cell
    python screen.py clear    blank every cell
    python screen.py text <cell> <text>

Every mode leaves the device in native mode only for the duration of the run.
"""

import sys
import time

from atomsq import (ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT, CELL_COUNT, CELLS,
                    ICONS, AtomSQ, target_from_argv)

# Distinct colours so adjacent cells are visually separable on the panel.
RAMP = [
    (0x7F, 0x00, 0x00), (0x7F, 0x40, 0x00), (0x7F, 0x7F, 0x00),
    (0x40, 0x7F, 0x00), (0x00, 0x7F, 0x00), (0x00, 0x7F, 0x40),
    (0x00, 0x7F, 0x7F), (0x00, 0x40, 0x7F), (0x00, 0x00, 0x7F),
    (0x40, 0x00, 0x7F), (0x7F, 0x00, 0x7F), (0x7F, 0x00, 0x40),
    (0x7F, 0x7F, 0x7F), (0x40, 0x40, 0x40),
]

WHITE = (0x7F, 0x7F, 0x7F)


def mode_map(device):
    """Each cell shows its own id. Photograph the panel to fix the layout."""
    for cell in range(CELL_COUNT):
        device.screen(cell, f"[{cell:X}]", RAMP[cell], ALIGN_CENTER)
    print("wrote cell ids 0..D. Read them off the panel and record the layout.")


def mode_names(device):
    """Write the claimed name of each cell into that cell.

    If the community layout is right, 'main1'/'main2' land on the two wide
    lines and bNlM land under soft button N.
    """
    for name, cell in CELLS.items():
        device.screen(cell, name, WHITE, ALIGN_CENTER)
    print("wrote claimed cell names. Any mismatch disproves the layout table.")


def mode_icons(device):
    """Render the private-font glyphs, a few per cell with their codes."""
    items = list(ICONS.items())
    per_cell = 2
    chunks = [items[i:i + per_cell] for i in range(0, len(items), per_cell)]
    for cell, chunk in enumerate(chunks):
        if cell >= CELL_COUNT:
            break
        text = "  ".join(f"{chr(code)}={code:02X}" for _name, code in chunk)
        device.screen(cell, text, WHITE, ALIGN_CENTER)
    for name, code in items:
        print(f"  0x{code:02X}  {name}")
    print("If a glyph renders, the icon font is real; blanks/garbage refute it.")


def mode_colors(device):
    for cell in range(CELL_COUNT):
        r, g, b = RAMP[cell]
        device.screen(cell, f"{r:02X}{g:02X}{b:02X}", RAMP[cell], ALIGN_CENTER)
    print("colour ramp written. Note any cells that ignore colour.")


def mode_align(device):
    for cell in range(CELL_COUNT):
        align = (ALIGN_LEFT, ALIGN_CENTER, ALIGN_RIGHT)[cell % 3]
        label = ("LEFT", "CENTER", "RIGHT")[cell % 3]
        device.screen(cell, label, WHITE, align)
    print("alignment cycled L/C/R across cells.")


def mode_len(device):
    """Walk text length up on the main line to find the real display limit.

    kMaxTextLength is 50 in the SDK, but that is a protocol cap, not proof the
    panel can show 50 characters.
    """
    for length in (4, 8, 12, 16, 20, 24, 32, 40, 50):
        text = ("123456789." * 6)[:length]
        device.screen(CELLS["main1"], text, WHITE, ALIGN_LEFT)
        device.screen(CELLS["main2"], f"len={length}", WHITE, ALIGN_CENTER)
        print(f"  len={length}: {text}")
        time.sleep(1.5)
    print("Watch where truncation starts - that is the real cell width.")


def mode_text(device, argv):
    if len(argv) < 2:
        print("usage: screen.py text <cell> <text>")
        return
    cell = int(argv[0], 0)
    device.screen(cell, " ".join(argv[1:]), WHITE, ALIGN_CENTER)


def main():
    target = target_from_argv()
    mode = sys.argv[1] if len(sys.argv) > 1 else "map"
    modes = {
        "map": mode_map, "names": mode_names, "icons": mode_icons,
        "colors": mode_colors, "align": mode_align, "len": mode_len,
    }

    with AtomSQ(target=target) as device:
        if mode == "clear":
            device.screen_clear()
            print("cleared")
        elif mode == "text":
            mode_text(device, sys.argv[2:])
        elif mode in modes:
            modes[mode](device)
        else:
            print(__doc__)
            return 1

        # Hold native mode open so the writes stay on screen to be read.
        # Releasing it hands the panel back to the device's own UI.
        hold(default=30.0)
    return 0


def hold(default: float) -> None:
    """Keep the device claimed so a human can look at it.

    Interactive: wait for Enter. Non-interactive (run by an agent or a script):
    wait ATOMSQ_HOLD seconds, defaulting to `default`, so the panel does not
    blank the instant the process exits.
    """
    import os
    override = os.environ.get("ATOMSQ_HOLD")
    seconds = float(override) if override else default
    if override is None:
        try:
            input("\npress Enter to release the device...")
            return
        except (EOFError, KeyboardInterrupt):
            # No usable stdin (agent/CI run) - fall through to a timed hold.
            pass
    print(f"\nholding for {seconds:g}s (set ATOMSQ_HOLD to change)...")
    time.sleep(seconds)


if __name__ == "__main__":
    sys.exit(main())
