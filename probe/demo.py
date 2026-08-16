#!/usr/bin/env python3
"""Reference integration — own the whole panel at once.

Paints a plausible controller UI using every documented surface: all 14 screen
cells with per-cell colour, alignment and private-font icons; 32 pads in a
colour scheme with blink and pulse; the 25-LED touch strip as a meter; and the
button LEDs. Then it reacts to input until you stop it.

This is the "we understand the device" proof, and the shape a real integration
takes.

    python demo.py                 hardware
    python demo.py --target sim    simulator
    python demo.py --both          both, so the sim mirrors the hardware
"""

import sys
import time

from atomsq import (ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT, BUTTONS, CELLS,
                    ICONS, PAD_COUNT, PAD_LED_BLINK, PAD_LED_ON, PAD_LED_PULSE,
                    AtomSQ, target_from_argv)
from listen import name_for

AMBER = (0x7F, 0x50, 0x00)
CYAN = (0x00, 0x6A, 0x7F)
GREEN = (0x10, 0x7F, 0x20)
MAGENTA = (0x7F, 0x00, 0x5A)
WHITE = (0x7F, 0x7F, 0x7F)

ICON = {name: chr(code) for name, code in ICONS.items()}

# Six soft-button labels: title on one line, value on the other. Cell ids come
# straight from the layout table in docs/PROTOCOL.md.
SOFT_BUTTONS = [
    ("b1l1", "b1l2", "TRACK", f"{ICON['arrow_left']} Drums {ICON['arrow_right']}", AMBER),
    ("b2l1", "b2l2", "DEVICE", f"{ICON['folder']} Bass", CYAN),
    ("b3l1", "b3l2", "SCALE", f"{ICON['note']} D min", GREEN),
    ("b4l1", "b4l2", "SWING", "56%", MAGENTA),
    ("b5l1", "b5l2", "LENGTH", f"1/16 {ICON['dot_small']}", CYAN),
    ("b6l1", "b6l2", "REC", f"{ICON['ok']} ARMED", (0x7F, 0x00, 0x00)),
]


def paint_screen(device):
    for title_cell, value_cell, title, value, color in SOFT_BUTTONS:
        device.screen(CELLS[title_cell], title, WHITE, ALIGN_CENTER)
        device.screen(CELLS[value_cell], value, color, ALIGN_CENTER)
    device.screen(CELLS["main1"],
                  f"{ICON['circle']} atomsq  {ICON['arrows_up_down']} pattern 3",
                  AMBER, ALIGN_LEFT)
    device.screen(CELLS["main2"], f"124.0 BPM  4/4  {ICON['power']} native",
                  CYAN, ALIGN_RIGHT)


def paint_pads(device):
    """Lower row = a 16-step sequencer, upper row = accents."""
    for step in range(16):
        active = step % 4 == 0
        device.pad_color(step, AMBER if active else (0x20, 0x10, 0x00))
        device.pad_state(step, PAD_LED_ON)
    for step in range(16):
        index = 16 + step
        device.pad_color(index, CYAN if step % 2 else MAGENTA)
        # Two pads animate so blink and pulse can be told apart at a glance.
        state = PAD_LED_ON
        if step == 4:
            state = PAD_LED_BLINK
        elif step == 12:
            state = PAD_LED_PULSE
        device.pad_state(index, state)


def paint_buttons(device):
    for name in ("A", "B", "C", "D"):
        device.button_color(BUTTONS[name], AMBER)
        device.button_led(BUTTONS[name], 127)
    for name in ("E", "F", "G", "H"):
        device.button_color(BUTTONS[name], CYAN)
        device.button_led(BUTTONS[name], 127)
    device.button_led(BUTTONS["play"], 127)
    device.button_led(BUTTONS["song"], 127)
    for name in ("lcd1", "lcd2", "lcd3", "lcd4", "lcd5", "lcd6"):
        device.button_led(BUTTONS[name], 127)


def main():
    target = target_from_argv()
    seconds = 90.0
    if "--seconds" in sys.argv:
        seconds = float(sys.argv[sys.argv.index("--seconds") + 1])

    with AtomSQ(target=target) as device:
        device.blackout()
        paint_screen(device)
        paint_pads(device)
        paint_buttons(device)
        print("panel painted; reacting to input. ctrl-c to stop.")

        start = time.time()
        meter = 0.0
        try:
            while time.time() - start < seconds:
                # Sweep the strip so the meter path is exercised continuously.
                meter = (meter + 0.02) % 1.0
                device.strip_meter(meter)
                for _delta, message in device.poll():
                    print(f"  {name_for(message)}")
                time.sleep(0.03)
        except KeyboardInterrupt:
            pass
        device.blackout()
    return 0


if __name__ == "__main__":
    sys.exit(main())
