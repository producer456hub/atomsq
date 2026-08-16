#!/usr/bin/env python3
"""Identity request -> firmware version, and a port inventory.

Read-only: does not enter native mode, so it cannot disturb the device.
"""

import sys

import rtmidi

from atomsq import IDENTITY_REQUEST, AtomSQ, PORT_NAME


def show_ports():
    print("MIDI ports")
    for label, midi in (("in ", rtmidi.MidiIn()), ("out", rtmidi.MidiOut())):
        for index, port in enumerate(midi.get_ports()):
            print(f"  {label} [{index}] {port}")
    print()


def main():
    show_ports()

    # native=False: we only want to ask its name, not take it over.
    with AtomSQ(native=False, verbose=False) as device:
        print(f"opened {PORT_NAME!r}")
        print("-> " + " ".join(f"{b:02X}" for b in IDENTITY_REQUEST))
        reply = device.identity(timeout=2.0)
        if reply is None:
            print("no identity reply within 2s")
            return 1
        print("<- " + " ".join(f"{b:02X}" for b in reply))
        print(f"   ({len(reply)} bytes, PreSonus's parser expects 17)")

        if len(reply) >= 15:
            # PreSonus reads these as BCD: parseInt(byte.toString(16)).
            major_raw, minor_raw = reply[13], reply[14]
            major = int(f"{major_raw:x}")
            minor = int(f"{minor_raw:x}")
            print(f"   firmware: {major}.{minor} "
                  f"(raw bytes 0x{major_raw:02X} 0x{minor_raw:02X}, read as BCD)")
            print(f"   naive decimal reading would be {major_raw}.{minor_raw} "
                  f"- USB bcdDevice 0x0117 says BCD is right")
        # Bytes 5-7 are the manufacturer ID in an identity reply.
        if len(reply) >= 8:
            mfr = " ".join(f"{b:02X}" for b in reply[5:8])
            print(f"   manufacturer id: {mfr} (expect 00 01 06 = PreSonus)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
