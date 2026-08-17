#!/usr/bin/env python3
"""Guided probe for the questions only a human looking at the panel can settle.

Each phase narrates itself on the device's own screen, so you can run it and
just watch the unit — no need to follow along in the terminal. At the end it
prints the questionnaire to answer.

    python answers.py                 all phases
    python answers.py compose         one phase
    ATOMSQ_PHASE=25 python answers.py  seconds per phase (default 15)

Phases:
    compose   does blink/pulse keep the pad's assigned colour?
    depth     how many brightness steps does the panel actually resolve?
    buttons   which buttons have real RGB LEDs, and which are on/off only?
    length    how many characters does a screen cell really show?
"""

import os
import sys
import time

from atomsq import (ALIGN_CENTER, ALIGN_LEFT, BUTTONS, CELLS, PAD_COUNT,
                    PAD_LED_BLINK, PAD_LED_ON, PAD_LED_PULSE, AtomSQ,
                    target_from_argv)
from leds import hsv

PHASE_SECONDS = float(os.environ.get("ATOMSQ_PHASE", 15))

WHITE = (0x7F, 0x7F, 0x7F)
AMBER = (0x7F, 0x50, 0x00)

# 50 unambiguous glyphs: the position of the last visible one is the answer.
RULER = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvw"


def narrate(device, line1, line2):
    device.screen(CELLS["main1"], line1, AMBER, ALIGN_CENTER)
    device.screen(CELLS["main2"], line2, WHITE, ALIGN_CENTER)


def phase_compose(device):
    """Distinct hue per pad, half blinking and half pulsing."""
    narrate(device, "TEST 1 of 4  blink + pulse",
            "colour kept, or overridden?")
    for index in range(PAD_COUNT):
        device.pad_color(index, hsv(index / PAD_COUNT))
        device.pad_state(index, PAD_LED_BLINK if index < 16 else PAD_LED_PULSE)
    print("phase 1 (compose): lower row blinks, upper row pulses, "
          "every pad a different hue")


def phase_depth(device):
    """Red ramp across the 32 pads — count the distinct steps."""
    narrate(device, "TEST 2 of 4  red ramp 0-124",
            "count the distinct steps")
    for index in range(PAD_COUNT):
        # 0, 4, 8 ... 124 across the pads, in note order.
        device.pad_color(index, (index * 4, 0, 0))
        device.pad_state(index, PAD_LED_ON)
    print("phase 2 (depth): pads carry red 0,4,8..124 in note order")
    print("  lower row = pads 1-16 (values 0-60), upper row = 17-32 (64-124)")


def phase_buttons(device):
    """Cycle every button through pure red, green, blue."""
    print("phase 3 (buttons): cycling every button R -> G -> B")
    for name, rgb in (("RED", (0x7F, 0, 0)), ("GREEN", (0, 0x7F, 0)),
                      ("BLUE", (0, 0, 0x7F))):
        narrate(device, "TEST 3 of 4  button LEDs",
                f"all buttons {name}")
        for cc in BUTTONS.values():
            device.button_color(cc, rgb)
            device.button_led(cc, 127)
        print(f"  all buttons -> {name}")
        time.sleep(PHASE_SECONDS / 3)


def _hold_buttons(device, label, rgb):
    """Drive every button to one colour and leave it there.

    Separate from phase_buttons because asking 'which buttons are green' about
    a static panel is answerable, while asking someone to track which of ~30
    buttons changed across a three-colour cycle is not.
    """
    narrate(device, "TEST 3 of 4  button LEDs", f"all buttons {label}")
    for cc in BUTTONS.values():
        device.button_color(cc, rgb)
        device.button_led(cc, 127)
    print(f"phase 3 ({label.lower()}): every button driven to {label} {rgb}")
    print("  buttons addressed: " + ", ".join(sorted(BUTTONS)))


def phase_buttons_green(device):
    # Green is the most diagnostic single colour: the panel's own idle states
    # are amber, white and red, so anything showing green is definitely
    # honouring our RGB write rather than sitting at a default.
    _hold_buttons(device, "GREEN", (0x00, 0x7F, 0x00))


def phase_buttons_blue(device):
    _hold_buttons(device, "BLUE", (0x00, 0x00, 0x7F))


def phase_buttons_red(device):
    _hold_buttons(device, "RED", (0x7F, 0x00, 0x00))


def phase_length(device):
    """A ruler in a wide cell and in a soft-button cell."""
    device.screen(CELLS["main1"], RULER, WHITE, ALIGN_LEFT)
    device.screen(CELLS["b1l1"], RULER, AMBER, ALIGN_LEFT)
    device.screen(CELLS["b1l2"], "^ soft cell", WHITE, ALIGN_CENTER)
    device.screen(CELLS["main2"], "TEST 4 of 4  last letter you can read?",
                  AMBER, ALIGN_CENTER)
    print("phase 4 (length): ruler written to main line 1 and to soft cell 1")
    print(f"  ruler = {RULER}")
    print("  A=1 B=2 ... Z=26, a=27 b=28 ... w=49")


def phase_buttons_white(device):
    """Drive every channel at once so each LED shows its own native colour.

    Asking "which are green" three times cannot see a fixed-red button, because
    it is lit during every pass and the question never asks about it. Driving
    R, G and B together lights everything that can light, in whatever colour it
    physically is, so one look gives the complete map.
    """
    _hold_buttons(device, "WHITE (all channels)", (0x7F, 0x7F, 0x7F))


# The right-hand cluster (soft buttons, nav, wheel arrows, shift, mode column)
# sits amber and ignores every colour we send - the device's own firmware is
# driving them for its menu UI. 0x13 is the community-reported "display /
# button-light ownership" flag, so if it hands the panel over, these should
# become ours.
RIGHT_CLUSTER = ["lcd1", "lcd2", "lcd3", "lcd4", "lcd5", "lcd6",
                 "up", "down", "left", "right",
                 "wheel_left", "wheel_right", "shift",
                 "song", "inst", "editor", "user"]


def phase_ownership(device):
    """Claim the panel with 0x13 = 01, then try to colour the amber cluster."""
    from modes import command

    print("phase (ownership): sending 0x13 = 01, then driving the right "
          "cluster GREEN")
    device.send(command(0x13, 0x01))
    time.sleep(0.3)
    narrate(device, "OWNERSHIP TEST 0x13=01", "right cluster -> GREEN")
    for name in RIGHT_CLUSTER:
        device.button_color(BUTTONS[name], (0x00, 0x7F, 0x00))
        device.button_led(BUTTONS[name], 127)
    print("  driven: " + ", ".join(RIGHT_CLUSTER))
    print("  if these turn green, 0x13 is the panel-ownership switch")


PHASES = {
    "compose": phase_compose,
    "depth": phase_depth,
    "buttons": phase_buttons,
    "green": phase_buttons_green,
    "blue": phase_buttons_blue,
    "red": phase_buttons_red,
    "white": phase_buttons_white,
    "own": phase_ownership,
    "length": phase_length,
}

QUESTIONS = """
------------------------------- questionnaire -------------------------------
1. compose  Did the blinking and pulsing pads keep their own colours, or did
            they all go to one colour / white?

2. depth    Roughly how many distinct brightness steps could you count across
            the 32 pads? (32 = full 7-bit resolution is being used; 8 or 16
            means the panel quantises hard; if the first few pads looked
            identical, note where it starts to change.)

3. buttons  Which buttons visibly changed colour across red/green/blue?
            Which stayed one fixed colour, and which lit but colourless?
            (Expect A-H to be RGB. Transport and the mode column are the
            interesting ones.)

4. length   What was the last letter readable on the wide main line, and on
            the small soft-button cell?
            A=1 ... Z=26, a=27 ... w=49
-----------------------------------------------------------------------------
"""


def main():
    target = target_from_argv()
    wanted = [a for a in sys.argv[1:] if not a.startswith("-")]
    order = wanted or ["compose", "depth", "buttons", "length"]
    for name in order:
        if name not in PHASES:
            print(f"unknown phase {name!r}; choose from {list(PHASES)}")
            return 1

    with AtomSQ(target=target) as device:
        device.blackout()
        for name in order:
            PHASES[name](device)
            # phase_buttons paces itself internally.
            if name != "buttons":
                time.sleep(PHASE_SECONDS)
            print()
        device.blackout()

    print(QUESTIONS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
