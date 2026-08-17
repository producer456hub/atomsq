# Status — updated 2026-08-16

The protocol work is done and verified on hardware, and the C++ core is written, built and
passing. What remains is one optional build check and a few curiosities that block nothing.

Hardware under test: PreSonus ATOM SQ, serial `ATSC20100175`, firmware **1.17**. Workspace is
mirrored to surfpad (`david@100.100.203.108:~/atomsq`) by `deploy-surfpad.sh`; the unit itself
moves between MAINTOP and surfpad, so check `lsusb`/MIDI ports before assuming where it is.

---

## What is settled

Everything below is verified on the actual unit, not inferred:

- **Screen** — `F0 00 01 06 22 12 <cell> <r> <g> <b> <align> <ascii> F7`. 14 cells, per-cell 7-bit
  RGB, alignment, and a private icon font at control codes `0x01`–`0x0B` / `0x1B`–`0x1F`. Cell
  layout confirmed by writing ids to the panel and reading them off.
- **Native mode** — claimed with `8F 00 7F`, released with `8F 00 00`.
- **`0x14` = nav-key capture** — A/B tested: 7 nav messages with the flag clear, 0 with it set
  while 19 other messages still flowed. That control is ours when we want it.
- **LEDs** — pad state on `0x90` (off/on/blink/pulse), colour selected by the *status channel*
  (`0x91`/`0x92`/`0x93` = R/G/B); buttons identical on `0xB1`/`0xB2`/`0xB3`. Touch strip is 25
  LEDs at CC 55–79.
- **Control map** — all 296 definitions, generated from PreSonus's own surface XML.
- **Pads transmit on MIDI channel 10**, while pad LED output is channel 1. Input and output
  channels differ — the vendor's own XML hides this behind a symbolic status.
- **Encoder acceleration** — the CC value is a speed-weighted magnitude (`+1 +2 +7 +12 +17 +22
  +27 +32`, decaying symmetrically), not a tick count.
- **Second MIDI port** (`ATM SQ Control`) — silent. Two minutes, every control, all four modes:
  199 messages on port 1, zero on port 2.
- **Buttons are not uniform.** Only nine of 30 take colour: A–H and Play are full RGB, Record is
  red-only, Metronome blue-only, and the whole right-hand cluster is firmware-owned amber that no
  host command reaches. `0x13` does not hand it over.
- **Screen capacity** — 25 characters on a main line, 7 in a soft cell, each plus a single ellipsis
  glyph the device appends itself. `kMaxTextLength = 50` is a message cap, not a display width.
- **Encoder direction** — sign-magnitude around `0x40`: `0x01` is +1, `0x41` is −1. The knobs are
  detentless, so the value can only ever be speed-weighted.
- **Animation composes with colour** — blink and pulse keep the pad's own hue.
- **The C++ core exists** — `core/`, C++17, no dependencies, 43 byte-level tests passing against
  `docs/PROTOCOL.md` with no hardware required.
- **Firmware is closed to us.** The chip is XMOS xCORE with a Thesycon DFU stack; the bootloader
  is `194f:020b` v0.15 and advertises `Upload Supported` but returns a 3-byte stub. Universal
  Control ships no images — it downloads them at runtime. Full account in `docs/FIRMWARE.md`.

---

## Pick up here

### 1. Run the C++ demo against the hardware

Everything builds: core, RtMidi adapter, tests (43 checks, 0 failures) and demo, all warning-free
with RtMidi 6.0.0. The one thing never done is running the demo with the device attached — it
needs the ATOM SQ plugged into the same machine as the build.

```bash
ssh -t david@100.100.203.108 "cd ~/atomsq/core && ./build/atomsq_demo"
```

With the unit on surfpad that should paint the panel exactly like `probe/demo.py` does, and print
every pad, button, encoder and strip event. That is the end-to-end proof that the C++ path and the
Python path agree.

If the unit is on MAINTOP instead, the demo reports the port it looked for and lists what it
found — which is how it behaved when tested.

### 2. Remaining protocol curiosities — all optional

None of these block anything:

- Exact LED bit depth. The ramp is smooth with no visible banding, so the full
  range is usable; the true step count was never counted.
- What the second MIDI port (`ATM SQ Control`) carries. Silent under every
  condition tried.
- Whether `0x13` hands over the amber cluster under some *other* ordering —
  colour writes before the flag, or with `0x14` also set. As tested, it does not.

### Optional, deliberate, not casual

Getting a firmware image would need disassembling `atomdevice.dll` to read the real
`XMOS_DFU_SELECTIMAGE` request number and arguments. **Do not go looking for it by probing request
numbers** — the XMOS vendor block is `0xF0`–`0xF6` and includes `REVERTFACTORY` at `0xf1`.

---

## Notes for whoever picks this up

- **`vendor/` is not in this repo.** It holds PreSonus's own device scripts, the SDK extracted
  from `musicdevices.dll`, the FaderPort family scripts and the manual's product render — all
  proprietary, so it is gitignored rather than published. Regenerate it from a machine with
  Studio One 7 installed:

  ```
  python vendor/extract_sdk.py
  ```

  and copy `C:\Program Files\PreSonus\Studio One 7\devices\PreSonus\ATOM` to
  `vendor/presonus-js`. The simulator's panel art comes from the owner's manual PDF and is
  likewise not redistributed here; `sim/layout.py` documents the geometry it was measured from.
  Without `vendor/`, `probe/parse_surface.py` and the simulator's photo background will not run —
  everything else does.
- **The device must be released.** It boots standalone and is claimed with `8F 00 7F`; always send
  `8F 00 00` when done. `AtomSQ.__exit__` does this even on exception.
- **Two machines.** Studio One only exists on MAINTOP (Windows) — that is where the vendor sources
  come from. surfpad (Linux) is where USB-level work happens: no driver binding, `dfu-util` works,
  and the USB string descriptors reveal port names Windows overwrites.
- **`amidi` gotcha:** `amidi -p PORT -S ... -d` races its own reply. Start the listener first.
