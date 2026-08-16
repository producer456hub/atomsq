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

from atomsq import ENCODERS, CC, AtomSQ, target_from_argv

ENCODER_NAMES = {cc: name for name, cc in ENCODERS.items()}

CAPTURE_SECONDS = 25.0
WAIT_SECONDS = 90.0


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


def main():
    target = target_from_argv()
    with AtomSQ(native=False, target=target, verbose=False) as device:
        print("Turn KNOB 1 slowly CLOCKWISE about 8 clicks,")
        print("then slowly COUNTER-CLOCKWISE about 8 clicks.")
        print("\nwaiting for the first encoder message...")
        first = wait_for_encoder(device)
        if first is None:
            print("nothing seen - is the right port open?")
            return 1
        print(f"got {ENCODER_NAMES[first[1]]} = 0x{first[2]:02X}; "
              f"capturing {CAPTURE_SECONDS:g}s")

        seen = collect(device, CAPTURE_SECONDS) + [
            (ENCODER_NAMES[first[1]], first[2])]

    if not seen:
        print("no encoder traffic captured")
        return 1

    print(f"\n{len(seen)} encoder messages")
    per_knob = Counter(name for name, _v in seen)
    for name, count in per_knob.most_common():
        raw = [v for n, v in seen if n == name]
        print(f"  {name}: {count} messages, raw "
              + " ".join(f"{v:02X}" for v in raw[:24])
              + (" ..." if len(raw) > 24 else ""))

    verdict([v for _n, v in seen])
    return 0


if __name__ == "__main__":
    sys.exit(main())
