#!/usr/bin/env python3
"""Pull PreSonus's control-surface SDK JavaScript out of musicdevices.dll.

The ATOM SQ device scripts open with

    include_file("resource://com.presonus.musicdevices/sdk/midiprotocol.js");
    include_file("resource://com.presonus.musicdevices/sdk/controlsurfacedevice.js");

Those files are not on disk — they are embedded in Studio One's musicdevices
plug-in as plain text. They define the base classes and constants the ATOM SQ
scripts are written against (PreSonus.Midi, ControlSurfaceDevice,
ControlHandler, PadSectionPadAnimation), so without them the vendored device
scripts are only half the story.

This is a Studio-One-on-Windows-only extraction; run it while the install is
reachable, not later.
"""

import re
import sys
from pathlib import Path

DLL = Path(r"C:\Program Files\PreSonus\Studio One 7\Plugins\musicdevices.dll")
OUT = Path(__file__).resolve().parent.parent / "vendor" / "presonus-sdk"

# Long runs of printable ASCII: each embedded script is one contiguous run.
BLOB = re.compile(rb"[\x09\x0a\x0d\x20-\x7e]{400,}")


def name_for(text: str, index: int) -> str:
    """Name a blob from its own banner.

    Each SDK blob carries a `Filename : foo.ts` line naming the TypeScript it
    was compiled from, which is far better than guessing from the first class.
    """
    banner = re.search(r"^//\s*Filename\s*:\s*(\S+?)\.ts\s*$", text,
                       re.MULTILINE)
    if banner:
        return f"{index:02d}_{banner.group(1).lower()}.js"
    first_class = re.search(r"\bclass\s+(\w+)", text)
    if first_class:
        return f"{index:02d}_{first_class.group(1).lower()}.js"
    return f"{index:02d}_blob.js"


def main():
    if not DLL.exists():
        sys.exit(f"not found: {DLL}\n"
                 "This extraction only works on a machine with Studio One.")
    data = DLL.read_bytes()
    OUT.mkdir(parents=True, exist_ok=True)

    blobs = [m for m in BLOB.finditer(data)]
    # Keep the script-looking ones; the DLL also holds unrelated ASCII tables.
    scripts = [m for m in blobs
               if b"class " in m.group() or b"include_file" in m.group()]
    scripts.sort(key=lambda m: m.start())

    print(f"{DLL.name}: {len(data)} bytes, {len(scripts)} script blobs\n")
    total = 0
    for index, match in enumerate(scripts, start=1):
        text = match.group().decode("ascii", "replace")
        path = OUT / name_for(text, index)
        path.write_text(text, encoding="utf-8")
        total += len(text)
        classes = re.findall(r"\bclass\s+(\w+)", text)
        print(f"  {path.name:<34} {len(text):>7} bytes @0x{match.start():X}")
        if classes:
            print(f"      classes: {', '.join(classes[:8])}"
                  + (" ..." if len(classes) > 8 else ""))
    print(f"\nwrote {total} bytes to {OUT}")


if __name__ == "__main__":
    main()
