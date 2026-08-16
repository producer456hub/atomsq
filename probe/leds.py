#!/usr/bin/env python3
"""LED probe — prove the pad/button colour encoding and the strip.

    python leds.py sweep      colour sweep across all 32 pads
    python leds.py primaries  R / G / B / white blocks, to judge white balance
    python leds.py states     off / on / blink / pulse side by side
    python leds.py compose    does blink/pulse keep the assigned colour?
    python leds.py depth      colour ramp on one pad to find real bit depth
    python leds.py buttons    colour every named button
    python leds.py strip      run the 25-LED strip as a meter
    python leds.py off        blackout

Add --target sim to drive the GUI simulator, or --both to mirror to both.
"""

import sys
import time

from atomsq import (BUTTONS, PAD_COUNT, PAD_LED_BLINK, PAD_LED_OFF,
                    PAD_LED_ON, PAD_LED_PULSE, STRIP_LED_COUNT, AtomSQ,
                    target_from_argv)


def hsv(hue: float):
    """Cheap HSV->7-bit RGB, full saturation and value."""
    hue = hue % 1.0
    sector = int(hue * 6) % 6
    frac = hue * 6 - int(hue * 6)
    top, rising, falling = 0x7F, int(0x7F * frac), int(0x7F * (1 - frac))
    return [(top, rising, 0), (falling, top, 0), (0, top, rising),
            (0, falling, top), (rising, 0, top), (top, 0, falling)][sector]


def mode_sweep(device):
    """Rainbow across the pads, then rotate it so motion is visible."""
    for step in range(60):
        for index in range(PAD_COUNT):
            device.pad_color(index, hsv(index / PAD_COUNT + step / 60))
            device.pad_state(index, PAD_LED_ON)
        time.sleep(0.05)
    print("swept. If colours are wrong, the ch2/3/4 mapping is wrong.")


def mode_primaries(device):
    """Eight-pad blocks of pure R, G, B, white.

    Studio One scales green by 0.8 and blue by 0.7 before sending, implying the
    raw primaries are not visually balanced. This shows the raw truth.
    """
    blocks = [((0x7F, 0, 0), "red"), ((0, 0x7F, 0), "green"),
              ((0, 0, 0x7F), "blue"), ((0x7F, 0x7F, 0x7F), "white")]
    for block, (rgb, name) in enumerate(blocks):
        for offset in range(8):
            index = block * 8 + offset
            device.pad_color(index, rgb)
            device.pad_state(index, PAD_LED_ON)
        print(f"  pads {block * 8:2d}-{block * 8 + 7:2d}: {name} {rgb}")
    print("Compare green/blue against red - that is why Studio One rescales.")


def mode_states(device):
    """Each quarter of the pad grid in one LED state."""
    states = [(PAD_LED_OFF, "off"), (PAD_LED_ON, "on"),
              (PAD_LED_BLINK, "blink"), (PAD_LED_PULSE, "pulse")]
    for block, (state, name) in enumerate(states):
        for offset in range(8):
            index = block * 8 + offset
            device.pad_color(index, (0x7F, 0x40, 0x00))
            device.pad_state(index, state)
        print(f"  pads {block * 8:2d}-{block * 8 + 7:2d}: {name} (0x{state:02X})")


def mode_compose(device):
    """Open question 4: do blink/pulse preserve the assigned colour?

    Give each pad a distinct hue, then put half into blink and half into pulse.
    If they animate in their own colour, animation composes with colour; if
    they all go white or default, it overrides.
    """
    for index in range(PAD_COUNT):
        device.pad_color(index, hsv(index / PAD_COUNT))
        device.pad_state(index,
                         PAD_LED_BLINK if index < PAD_COUNT // 2 else PAD_LED_PULSE)
    print("first 16 pads blink, last 16 pulse, each a different hue.")
    print("Colour retained => animation composes. All same colour => overrides.")


def mode_depth(device):
    """Ramp one pad through every red value to see where steps appear."""
    index = 0
    device.pad_state(index, PAD_LED_ON)
    print("ramping pad 0 red 0->127; count the distinct steps you can see")
    for value in range(0, 0x80, 1):
        device.pad_color(index, (value, 0, 0))
        time.sleep(0.06)
    print("7 bits are sent, but the panel may quantise to far fewer.")


def mode_buttons(device):
    for offset, (name, cc) in enumerate(BUTTONS.items()):
        device.button_color(cc, hsv(offset / len(BUTTONS)))
        device.button_led(cc, 127)
    print(f"coloured {len(BUTTONS)} buttons. Note which ones ignore colour - "
          "not every button on the panel has an RGB LED.")


def mode_strip(device):
    print("running the strip as a meter")
    for _cycle in range(3):
        for step in range(STRIP_LED_COUNT):
            device.strip_meter(step / (STRIP_LED_COUNT - 1))
            time.sleep(0.04)
        for step in reversed(range(STRIP_LED_COUNT)):
            device.strip_meter(step / (STRIP_LED_COUNT - 1))
            time.sleep(0.04)
    device.strip_off()


def main():
    target = target_from_argv()
    mode = sys.argv[1] if len(sys.argv) > 1 else "sweep"
    modes = {
        "sweep": mode_sweep, "primaries": mode_primaries, "states": mode_states,
        "compose": mode_compose, "depth": mode_depth, "buttons": mode_buttons,
        "strip": mode_strip,
    }

    with AtomSQ(target=target) as device:
        if mode == "off":
            device.blackout()
            print("blackout")
        elif mode in modes:
            device.blackout()
            modes[mode](device)
            hold()
        else:
            print(__doc__)
            return 1
        device.blackout()
    return 0


def hold(default: float = 20.0):
    import os
    override = os.environ.get("ATOMSQ_HOLD")
    seconds = float(override) if override else default
    if override is None:
        try:
            input("\npress Enter to release the device...")
            return
        except (EOFError, KeyboardInterrupt):
            pass
    print(f"\nholding for {seconds:g}s (set ATOMSQ_HOLD to change)...")
    time.sleep(seconds)


if __name__ == "__main__":
    sys.exit(main())
