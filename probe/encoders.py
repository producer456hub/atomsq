#!/usr/bin/env python3
"""Settle how the endless encoders encode direction.

surface.xml declares all nine as `type="relative" options="signed plain"`. Two
readings of that fit the observed positive values and disagree on reverse:

  sign-magnitude around 0x40   0x01..0x3F forward, 0x41..0x7F reverse
  two's complement             0x01..0x3F forward, 0x7F..0x41 reverse

They differ in where reverse values *cluster*. A slow reverse turn produces
small magnitudes, which lands just above 0x40 under sign-magnitude and just
below 0x80 under two's complement. That is the discriminator, and it is
decidable without anyone eyeballing anything.

Self-paced: it waits for the first encoder message, so the timer cannot expire
before you reach the device.

    python encoders.py
"""

import sys
import time
from collections import Counter

from atomsq import (ALIGN_CENTER, CELLS, ENCODERS, CC, ICONS, AtomSQ,
                    target_from_argv)

ENCODER_NAMES = {cc: name for name, cc in ENCODERS.items()}

CAPTURE_SECONDS = 12.0
WAIT_SECONDS = 240.0

AMBER = (0x7F, 0x50, 0x00)
GREEN = (0x10, 0x7F, 0x20)
WHITE = (0x7F, 0x7F, 0x7F)

ARROW_R = chr(ICONS["arrow_right"])
ARROW_L = chr(ICONS["arrow_left"])


def say(device, line1, line2, color=AMBER):
    """Put the instructions on the device's own screen.

    The terminal is not visible when this runs in the background, and the unit
    is across the desk — so it narrates itself. This is also the first real use
    of the screen protocol for something other than a demo.
    """
    if device is None:
        return
    device.screen(CELLS["main1"], line1, color, ALIGN_CENTER)
    device.screen(CELLS["main2"], line2, WHITE, ALIGN_CENTER)


def is_encoder(message):
    return (len(message) >= 3 and (message[0] & 0xF0) == CC
            and message[1] in ENCODER_NAMES)


def wait_for_encoder(device, timeout=WAIT_SECONDS):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for _delta, message in device.poll():
            if is_encoder(message):
                return message
        time.sleep(0.005)
    return None


def collect(device, seconds):
    seen = []
    deadline = time.time() + seconds
    while time.time() < deadline:
        for _delta, message in device.poll():
            if is_encoder(message):
                seen.append((ENCODER_NAMES[message[1]], message[2]))
        time.sleep(0.003)
    return seen


def verdict(values):
    low = [v for v in values if 0x01 <= v <= 0x3F]      # forward, either way
    high = [v for v in values if v >= 0x41]             # the interesting half
    print(f"\nforward-range values (0x01-0x3F): {len(low)}")
    print(f"reverse-range values (0x41-0x7F): {len(high)}")

    if not high:
        print("\nINCONCLUSIVE — no values above 0x40 were seen, so only one")
        print("direction got exercised. Re-run and turn the knob both ways.")
        return

    near_40 = sum(1 for v in high if v <= 0x50)   # sign-magnitude: 0x41, 0x42…
    near_7f = sum(1 for v in high if v >= 0x70)   # two's complement: 0x7F, 0x7E…
    print(f"  clustered just above 0x40 (<=0x50): {near_40}")
    print(f"  clustered just below 0x80 (>=0x70): {near_7f}")

    print("\n--- result ---")
    if near_40 > near_7f:
        print("SIGN-MAGNITUDE around 0x40.")
        print("  decode:  v < 0x40  ->  +v")
        print("            v > 0x40  ->  -(v - 0x40)")
        print("  This matches the decode_relative() already in atomsq.py.")
    elif near_7f > near_40:
        print("TWO'S COMPLEMENT.")
        print("  decode:  v < 0x40  ->  +v")
        print("            v >= 0x40 ->  v - 0x80")
        print("  atomsq.py's decode_relative() is WRONG and must be fixed -")
        print("  reverse turns would come out with the wrong magnitude.")
    else:
        print("AMBIGUOUS - values did not cluster. Turn more slowly; fast")
        print("turns push magnitudes into the middle where the two readings")
        print("overlap.")


def phase(device, label, instruction, screen1, screen2, seconds=CAPTURE_SECONDS):
    """Capture one single-direction turn, self-paced, narrated on the panel."""
    print(f"\n--- {label} ---")
    print(f"  {instruction}")
    print("  (waiting for you to start...)")
    say(device, screen1, screen2)
    first = wait_for_encoder(device)
    if first is None:
        print("  nothing seen")
        say(device, "TIMED OUT", "no knob movement seen")
        return []
    print(f"  started; capturing {seconds:g}s — keep turning THE SAME WAY")
    say(device, screen1, f"KEEP TURNING  {seconds:g}s", GREEN)
    seen = [(ENCODER_NAMES[first[1]], first[2])] + collect(device, seconds)
    raw = [v for _n, v in seen]
    print(f"  {len(raw)} messages, raw: "
          + " ".join(f"{v:02X}" for v in raw[:30])
          + (" ..." if len(raw) > 30 else ""))
    if raw:
        print(f"  range 0x{min(raw):02X}-0x{max(raw):02X}")
    return seen


def main():
    target = target_from_argv()
    print("Two separate turns, ONE DIRECTION EACH. The previous single-capture")
    print("version could not tell a direction change from the acceleration")
    print("curve ramping back down, so each direction now gets its own phase.")

    # native=True so the screen can be written; the encoders report the same
    # way either mode, and the standalone-mode capture is on record to compare.
    with AtomSQ(native=True, target=target, verbose=False) as device:
        say(device, "ENCODER TEST", "starting...")
        time.sleep(1.5)
        cw = phase(device, "PHASE 1 of 2",
                   "Turn KNOB 1 slowly CLOCKWISE ONLY.",
                   f"KNOB 1  CLOCKWISE {ARROW_R}", "turn it now, slowly")
        print("\n  ...pause. Take your hand off the knob for a moment.")
        say(device, "STOP", "hands off the knob", WHITE)
        time.sleep(4)
        # Drain the tail of phase 1 so it cannot leak into phase 2.
        collect(device, 1.0)
        ccw = phase(device, "PHASE 2 of 2",
                    "Now turn KNOB 1 slowly COUNTER-CLOCKWISE ONLY.",
                    f"{ARROW_L} KNOB 1  COUNTER-CW", "now the other way")
        say(device, "DONE", "thanks", GREEN)
        time.sleep(2)

    if not cw or not ccw:
        print("\nneed both directions to decide - re-run")
        return 1

    cw_raw = [v for _n, v in cw]
    ccw_raw = [v for _n, v in ccw]
    print("\n=== comparison ===")
    print(f"  clockwise:         range 0x{min(cw_raw):02X}-0x{max(cw_raw):02X}")
    print(f"  counter-clockwise: range 0x{min(ccw_raw):02X}-0x{max(ccw_raw):02X}")

    # Whichever direction produced values above 0x40 is the negative one.
    reverse = ccw_raw if max(ccw_raw) > 0x40 else cw_raw
    if max(cw_raw) <= 0x40 and max(ccw_raw) <= 0x40:
        print("\n--- result ---")
        print("BOTH directions stayed under 0x40. Direction is NOT carried in")
        print("the CC value at all - which means it must be signalled some")
        print("other way, and every assumption in decode_relative() is wrong.")
        print("Check whether the two directions used different CC numbers.")
        cw_ccs = {n for n, _v in cw}
        ccw_ccs = {n for n, _v in ccw}
        print(f"  clockwise controls:         {sorted(cw_ccs)}")
        print(f"  counter-clockwise controls: {sorted(ccw_ccs)}")
        return 0

    verdict(reverse)
    return 0


if __name__ == "__main__":
    sys.exit(main())
