#!/usr/bin/env python3
"""What is the second MIDI port for?

The ATOM SQ enumerates two port pairs. PreSonus's own .device file names
"ATM SQ" as the detectorPortName, so that is the control/native port. The
second pair (MIDIIN2/MIDIOUT2) is undocumented in anything we have.

This opens both at once and labels every message with the port it arrived on,
which is the only way to tell whether they carry the same stream, split
control from performance data, or one is a MIDI thru.

    python ports.py                 listen on both for 45s
    python ports.py --seconds 90
    python ports.py --native        claim native mode on port 1 first

Press pads, buttons, knobs and the touch strip, then switch modes with
Song/Inst/Editor/User and press things again. Mode-dependent routing is
exactly the sort of thing a second port exists for.
"""

import sys
import time
from collections import Counter

import rtmidi

from atomsq import NATIVE_OFF, NATIVE_ON, describe
from listen import name_for

PORTS = ["ATM SQ", "MIDIIN2"]


def open_inputs():
    """Open every ATOM SQ input port, returning (label, MidiIn)."""
    opened = []
    probe = rtmidi.MidiIn()
    available = probe.get_ports()
    del probe
    for index, name in enumerate(available):
        if "ATM SQ" not in name:
            continue
        midi = rtmidi.MidiIn()
        midi.open_port(index)
        midi.ignore_types(sysex=False, timing=False, active_sense=False)
        label = "port1" if name.startswith("ATM SQ") else "port2"
        opened.append((label, name, midi))
        print(f"  opened {label}: {name}")
    return opened


def find_output(fragment):
    midi = rtmidi.MidiOut()
    for index, name in enumerate(midi.get_ports()):
        if name.startswith(fragment):
            midi.open_port(index)
            return midi
    del midi
    return None


def main():
    argv = sys.argv[1:]
    seconds = 45.0
    if "--seconds" in argv:
        seconds = float(argv[argv.index("--seconds") + 1])
    native = "--native" in argv

    print("opening every ATOM SQ input port")
    inputs = open_inputs()
    if len(inputs) < 2:
        print("\nonly one input port found - nothing to compare")
        return 1

    control_out = find_output("ATM SQ") if native else None
    if control_out:
        control_out.send_message(NATIVE_ON)
        print("  [native mode ON via port1]")

    print(f"\nlistening {seconds:g}s. Exercise the panel, then change mode "
          f"(Song/Inst/Editor/User) and exercise it again.")
    print("-" * 76)

    counts = Counter()
    kinds = {}
    deadline = time.time() + seconds
    try:
        while time.time() < deadline:
            for label, _name, midi in inputs:
                while True:
                    item = midi.get_message()
                    if item is None:
                        break
                    message, _delta = item
                    counts[label] += 1
                    kinds.setdefault(label, Counter())[
                        message[0] & 0xF0 if message else 0] += 1
                    print(f"  {label}  {describe(message):<34} "
                          f"{name_for(message)}")
            time.sleep(0.002)
    except KeyboardInterrupt:
        pass
    finally:
        if control_out:
            control_out.send_message(NATIVE_OFF)
            print("\n  [native mode OFF]")
            control_out.close_port()
        for _label, _name, midi in inputs:
            midi.close_port()

    print("-" * 76)
    print("\nmessages per port:")
    for label, count in counts.items():
        breakdown = ", ".join(f"0x{status:02X}x{n}"
                              for status, n in kinds[label].items())
        print(f"  {label}: {count}   ({breakdown})")
    if not counts.get("port2"):
        print("\nport2 stayed silent - it is not a duplicate of the control "
              "stream. Likely the plain MIDI-mode / thru port, only active in "
              "a mode we did not enter.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
