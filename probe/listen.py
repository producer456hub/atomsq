#!/usr/bin/env python3
"""Input probe — capture everything the device sends and name it.

    python listen.py                 raw stream, decoded and named
    python listen.py --map           collect a control map, then diff it
                                     against the surface.xml-derived map
    python listen.py --seconds 120   how long to run (default 60)
    python listen.py --native        claim native mode first (changes what
                                     the nav keys and mode buttons emit)

The --map run is the verification step for docs/CONTROL_MAP.md: press every
control once, and anything observed-but-undocumented or documented-but-silent
is reported as a discrepancy rather than quietly reconciled.
"""

import sys
import time
from collections import Counter, OrderedDict

from atomsq import (BUTTONS, CC, ENCODERS, NOTE_ON, NOTE_OFF, PAD_COUNT,
                    PAD_NOTE_START, PAD_PRESSURE_CC, PITCH_BEND, POLY_AT,
                    STRIP_LED_COUNT, STRIP_LED_START, AtomSQ, decode_relative,
                    describe, target_from_argv)

CC_NAMES = {cc: name for name, cc in BUTTONS.items()}
ENCODER_NAMES = {cc: name for name, cc in ENCODERS.items()}


def name_for(message) -> str:
    """Explain a message using the documented map, or say we cannot."""
    if not message or message[0] == 0xF0:
        return "sysex"
    status = message[0]
    kind, channel = status & 0xF0, (status & 0x0F) + 1
    if len(message) < 3:
        return "short message"
    addr, value = message[1], message[2]

    if kind in (NOTE_ON, NOTE_OFF):
        index = addr - PAD_NOTE_START
        if 0 <= index < PAD_COUNT:
            row, col = divmod(index, 16)
            return f"pad[{row}][{col}] vel={value}"
        if addr == 0x00:
            return f"function pad + (vel={value})"
        if addr == 0x01:
            return f"function pad - (vel={value})"
        return f"UNKNOWN note {addr:#04x}"

    if kind == POLY_AT:
        if addr in (0x00, 0x01):
            sign = "+" if addr == 0x00 else "-"
            return f"function pad {sign} pressure={value}"
        index = addr - PAD_NOTE_START
        if 0 <= index < PAD_COUNT:
            return f"pad[{index // 16}][{index % 16}] pressure={value}"
        return f"UNKNOWN poly-at {addr:#04x}"

    if kind == PITCH_BEND:
        return f"touch strip = {addr | (value << 7)} (14-bit)"

    if kind == CC:
        if addr in ENCODER_NAMES:
            delta = decode_relative(value)
            return (f"{ENCODER_NAMES[addr]} delta={delta:+d} "
                    f"(raw {value:#04x})")
        if addr in CC_NAMES:
            action = "press" if value >= 64 else "release"
            return f"{CC_NAMES[addr]} {action} ({value})"
        if addr == PAD_PRESSURE_CC:
            return f"global pad pressure={value}"
        if STRIP_LED_START <= addr < STRIP_LED_START + STRIP_LED_COUNT:
            return f"strip LED echo {addr - STRIP_LED_START}"
        return f"UNKNOWN cc {addr:#04x} = {value}"

    return f"UNKNOWN status {status:#04x}"


def documented_addresses():
    """Every (kind, address) pair our docs claim the device can send."""
    known = set()
    for cc in list(BUTTONS.values()) + list(ENCODERS.values()):
        known.add(("cc", cc))
    known.add(("cc", PAD_PRESSURE_CC))
    for index in range(PAD_COUNT):
        known.add(("note", PAD_NOTE_START + index))
    known.add(("note", 0x00))
    known.add(("note", 0x01))
    return known


def observed_key(message):
    """Reduce a message to the (kind, address) identity used for diffing."""
    if not message or message[0] == 0xF0 or len(message) < 3:
        return None
    kind = message[0] & 0xF0
    if kind in (NOTE_ON, NOTE_OFF):
        return ("note", message[1])
    if kind == POLY_AT:
        return ("note", message[1])
    if kind == CC:
        return ("cc", message[1])
    if kind == PITCH_BEND:
        return ("bend", 0)
    return ("?", message[1])


def main():
    target = target_from_argv()
    argv = sys.argv[1:]
    do_map = "--map" in argv
    native = "--native" in argv
    seconds = 60.0
    if "--seconds" in argv:
        seconds = float(argv[argv.index("--seconds") + 1])

    counts = Counter()
    first_seen = OrderedDict()

    print(f"listening for {seconds:g}s"
          + (" in native mode" if native else " (standalone)"))
    if do_map:
        print("MAP RUN: press every pad, button, knob and the touch strip once.")
    print("-" * 72)

    with AtomSQ(native=native, target=target, verbose=native) as device:
        deadline = time.time() + seconds
        while time.time() < deadline:
            for _delta, message in device.poll():
                key = observed_key(message)
                if key:
                    counts[key] += 1
                    if key not in first_seen:
                        first_seen[key] = name_for(message)
                if not do_map:
                    print(f"  {describe(message):<34} {name_for(message)}")
            time.sleep(0.002)

    print("-" * 72)
    if not do_map:
        return 0

    print(f"\n{len(first_seen)} distinct controls seen\n")
    for key, label in first_seen.items():
        kind, addr = key
        print(f"  {kind:<5} {addr:#04x}  x{counts[key]:<5} {label}")

    documented = documented_addresses()
    seen = {k for k in first_seen if k[0] in ("cc", "note")}
    undocumented = sorted(seen - documented)
    silent = sorted(documented - seen)

    print("\n--- diff against docs/CONTROL_MAP.md ---")
    if undocumented:
        print(f"\nOBSERVED BUT UNDOCUMENTED ({len(undocumented)}):")
        for kind, addr in undocumented:
            print(f"  {kind} {addr:#04x} — investigate, this is a real finding")
    else:
        print("\nnothing observed that the docs do not explain")

    if silent:
        print(f"\nDOCUMENTED BUT NOT SEEN ({len(silent)}):")
        print("  (expected if you did not touch every control)")
        for kind, addr in silent:
            print(f"  {kind} {addr:#04x}")
    else:
        print("\nevery documented control was exercised")
    return 0


if __name__ == "__main__":
    sys.exit(main())
