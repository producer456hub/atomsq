#!/usr/bin/env python3
"""Install a traced clone of the ATOM SQ device into Studio One's user folder.

Studio One's ATOM SQ support is plain JavaScript, so it can be made to narrate
itself. This clones the stock device into
%APPDATA%\\PreSonus\\Studio One 7\\devices\\ under a new name and classID, then
wraps the MIDI entry points so every byte Studio One sends to the unit — and
every byte it receives — is written to the host console.

Nothing under Program Files is touched, so no elevation is needed and the stock
device keeps working. Uninstalling is deleting one folder.

    python install_trace_device.py --install
    python install_trace_device.py --uninstall

Then in Studio One: Options > External Devices > Add, pick
PreSonus > ATOM SQ (trace), and set both its ports to "ATM SQ".

Caveat: output goes to Host.Console.writeLine. The script sandbox exposes no
file API, so if Studio One's console is not visible in your build, this yields
nothing — check before relying on it.
"""

import argparse
import os
import re
import shutil
import sys
import uuid
from pathlib import Path

STOCK = Path(r"C:\Program Files\PreSonus\Studio One 7\devices\PreSonus\ATOM")
USER_DEVICES = Path(os.environ["APPDATA"]) / "PreSonus" / "Studio One 7" / "devices"
TARGET = USER_DEVICES / "PreSonus" / "ATOM SQ Trace"

DEVICE_NAME = "ATOM SQ (trace)"

# Wrappers appended to the cloned device script. They chain to the originals,
# so behaviour is unchanged apart from the logging.
TRACE_JS = """

//============================================================================
// Tracing added for reverse engineering. Wraps the MIDI entry points so the
// full host<->device dialogue is visible. Chains to the originals, so the
// device behaves exactly as stock.
//============================================================================

function atomsqHex (data)
    {
    var out = "";
    for (var i = 0; i < data.length; i++)
        {
        var b = data[i] & 0xFF;
        out += (b < 16 ? "0" : "") + b.toString (16).toUpperCase () + " ";
        }
    return out;
    }

(function ()
{
    var proto = ATOMSQMidiDevice.prototype;

    var baseInit = proto.onInit;
    proto.onInit = function (hostDevice)
        {
        baseInit.call (this, hostDevice);
        this.debugLog = true;
        this.log ("[trace] ATOM SQ trace device initialised");
        };

    var baseSendMidi = proto.sendMidi;
    if (baseSendMidi)
        proto.sendMidi = function (status, data1, data2)
            {
            this.log ("[trace] OUT  " + atomsqHex ([status, data1, data2]));
            return baseSendMidi.call (this, status, data1, data2);
            };

    var baseSendSysex = proto.sendSysex;
    if (baseSendSysex)
        proto.sendSysex = function (buffer)
            {
            this.log ("[trace] OUT SYSEX " + buffer);
            return baseSendSysex.call (this, buffer);
            };

    var baseMidiEvent = proto.onMidiEvent;
    if (baseMidiEvent)
        proto.onMidiEvent = function (status, data1, data2)
            {
            this.log ("[trace] IN   " + atomsqHex ([status, data1, data2]));
            return baseMidiEvent.call (this, status, data1, data2);
            };

    var baseSysexEvent = proto.onSysexEvent;
    if (baseSysexEvent)
        proto.onSysexEvent = function (data, length)
            {
            this.log ("[trace] IN SYSEX  " + atomsqHex (data));
            return baseSysexEvent.call (this, data, length);
            };

    var baseConnected = proto.onMidiOutConnected;
    if (baseConnected)
        proto.onMidiOutConnected = function (state)
            {
            this.log ("[trace] midi out connected = " + state);
            return baseConnected.call (this, state);
            };
})();
"""


def install():
    if not STOCK.exists():
        sys.exit(f"stock device not found: {STOCK}\nStudio One 7 required.")
    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.parent.mkdir(parents=True, exist_ok=True)

    # The device folder references "../Shared", so bring the whole tree.
    shutil.copytree(STOCK, TARGET)
    print(f"copied stock device -> {TARGET}")

    # Point the definition at a fresh identity so it sits beside the stock one
    # instead of colliding with it.
    definition = TARGET / "ATOM SQ.device"
    text = definition.read_text(encoding="utf-8")
    text = text.replace('name="ATOM SQ"', f'name="{DEVICE_NAME}"')
    text = re.sub(r'classID="\{[^}]+\}"',
                  f'classID="{{{str(uuid.uuid4()).upper()}}}"', text)
    definition.write_text(text, encoding="utf-8")
    print(f"renamed to {DEVICE_NAME!r} with a new classID")

    # Drop the sibling ATOM (non-SQ) definition so only the traced SQ appears.
    for stray in ("ATOM.device",):
        path = TARGET / stray
        if path.exists():
            path.unlink()

    script = TARGET / "ATOM SQ" / "ATOMSQMidiDevice.js"
    script.write_text(script.read_text(encoding="utf-8") + TRACE_JS,
                      encoding="utf-8")
    print(f"appended tracing wrappers to {script.name}")

    print("\nNext: restart Studio One, then")
    print("  Options > External Devices > Add > PreSonus > " + DEVICE_NAME)
    print("  set Receive From and Send To both to 'ATM SQ'")
    print("Then watch the console for [trace] lines.")


def uninstall():
    if TARGET.exists():
        shutil.rmtree(TARGET)
        print(f"removed {TARGET}")
    else:
        print("nothing installed")
    # Clean up the empty scaffolding we may have created.
    for folder in (TARGET.parent, USER_DEVICES):
        try:
            folder.rmdir()
            print(f"removed empty {folder}")
        except OSError:
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()
    if args.uninstall:
        uninstall()
    elif args.install:
        install()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
