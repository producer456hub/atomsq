# atomsq

Owning the PreSonus ATOM SQ at the protocol level, so it can be a first-class controller for
software we write — full authorship of its screen, pads and LEDs, not just DAW mappings.

Unit under test: serial `ATSC20100175`, firmware **1.17**, `VID 0x194F` / `PID 0x020A`.

## What's here

**Parked 2026-08-16 — see [STATUS.md](STATUS.md) for where it got to and what to pick up first.**

| path | what |
|---|---|
| `STATUS.md` | Where this stopped, what is settled, what is next. Start here. |
| `docs/PROTOCOL.md` | The reference. Every fact tagged **[V]**erified / **[C]**ommunity / **[?]**inferred. |
| `docs/FIRMWARE.md` | DFU, the XMOS/Thesycon stack, and why a firmware dump is closed to us. |
| `docs/CONTROL_MAP.md` | All 296 control definitions, generated from PreSonus's own surface file. |
| `probe/` | Python harness that proves the protocol against real hardware. |
| `sim/` | GUI simulator — develop with no hardware, and see exactly what our bytes do. |
| `tools/` | udev rule, DFU dump script, and the extractors that rebuild `vendor/`. |
| `core/` | Portable C++ library (not started). |

## How this was worked out, and what is missing from this repo

Studio One ships its ATOM SQ control-surface implementation as **unobfuscated JavaScript**, and
the SDK those scripts are written against is embedded as plain text inside `musicdevices.dll`.
`ATOMSQProtocol.js`, `ATOMSQMidiDevice.js` and `ATOM SQ.surface.xml` are first-party sources for
the screen protocol, the LED encoding and the complete control map. Most of `docs/PROTOCOL.md`
was read out of them rather than guessed at with a MIDI monitor — and then confirmed against the
hardware, which caught things the source alone did not (pads transmit on channel 10, not 1).

**That material is not in this repo.** It is PreSonus/Fender's copyrighted code and artwork, so
publishing it is not ours to do. `vendor/`, `sim/assets/` and `captures/` are gitignored.
Rebuild them locally on a machine with Studio One 7:

```bash
python tools/extract_sdk.py     # pulls the SDK out of musicdevices.dll
# and copy the device scripts:
#   "C:\Program Files\PreSonus\Studio One 7\devices\PreSonus\ATOM"  ->  vendor/presonus-js
```

The simulator's panel background is the top-down render from the owner's manual PDF; extract it
into `sim/assets/atomsq_topdown.png` yourself. `sim/layout.py` documents the geometry measured
from it, so the coordinates survive without the image.

Without those, `probe/parse_surface.py` and the simulator's photo background will not run.
Everything else does.

## Quick start

Needs `python-rtmidi`; the simulator's photo overlay additionally needs `pillow`.

```bash
python probe/identity.py               # firmware version, port inventory
python probe/hold.py                   # do buttons send a release? (they do)
python probe/listen.py --map           # press everything, diff against the docs
python probe/screen.py map             # write each cell's id to the screen
python probe/leds.py sweep             # rainbow across the 32 pads
python probe/parse_surface.py          # regenerate docs/CONTROL_MAP.md
```

Every probe takes a target:

```bash
python probe/leds.py sweep --target sim    # simulator only, no hardware
python probe/leds.py sweep --both          # hardware and simulator together
```

`ATOMSQ_HOLD=30` sets how long a probe keeps the device claimed before releasing it (used when
running non-interactively).

## Simulator

```bash
python sim/atomsq_sim.py                 # then drive it with --target sim
python sim/atomsq_sim.py --calibrate     # alignment outlines on the artwork
```

The panel is drawn **on the official top-down render**, extracted from the owner's manual PDF into
`sim/assets/`. Every live element — 14 screen cells, 32 pads with blink/pulse, the 25-LED strip,
every button — is registered to that photo, so layout compliance is checked continuously: if a
drawn control does not sit on its printed counterpart, the geometry is wrong.

The geometry itself is **measured, not eyeballed**. `sim/measure.py` scans lines across the render
and extracts the runs of saturated pixels, giving exact edges for every pad, button and LED; it
prints numbers ready to paste into `sim/layout.py`.

Clicking a pad or button sends real input back to the driving script, and the mouse wheel over a
knob emits relative deltas. Keys: `c` calibration outlines, `g` hide the photo, `l` labels,
`q` quit.

Anything the simulator cannot explain increments an **unexplained** counter on the status line —
that counter is the point. If it moves, our understanding of the protocol has a hole in it.

`sim/shot.ps1` captures the window to a PNG, so alignment can be checked without a human at the
screen.

## Safety

- The device boots standalone and must be claimed with `8F 00 7F`. **Always release it with
  `8F 00 00`** — `AtomSQ` does this from `__exit__` even on exception.
- Nothing here writes firmware. The DFU interface is enumerated read-only; see `docs/FIRMWARE.md`.
