# Status — parked 2026-08-16

Where this got to, and what to pick up first. The protocol work is essentially done and verified
on hardware; what remains is a short list of cheap experiments and then writing the C++ core.

Hardware under test: PreSonus ATOM SQ, serial `ATSC20100175`, firmware **1.17**, currently
attached to **surfpad** (`david@100.100.203.108`, workspace `~/atomsq`).

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
- **Firmware is closed to us.** The chip is XMOS xCORE with a Thesycon DFU stack; the bootloader
  is `194f:020b` v0.15 and advertises `Upload Supported` but returns a 3-byte stub. Universal
  Control ships no images — it downloads them at runtime. Full account in `docs/FIRMWARE.md`.

---

## Pick up here

### 1. Encoder direction — 2 minutes, and it matters

The only unresolved thing that would produce a *wrong* library. Every delta captured so far was
positive because the test turns only went one way.

```bash
ssh david@100.100.203.108
cd atomsq/probe && python3 encoders.py
# turn knob 1 slowly clockwise ~8 clicks, then slowly counter-clockwise ~8 clicks
```

It waits for knob traffic (no timer to race) and prints the verdict. `decode_relative()` in
`probe/atomsq.py` assumes **sign-magnitude around 0x40**; if the answer is two's complement that
function is wrong and every reverse turn yields a nonsense magnitude — a bug that presents as
"the knob feels jumpy", not as a decode error.

### 2. The four visual questions — 75 seconds of watching

```bash
cd atomsq/probe && python3 answers.py
```

Each phase narrates itself on the device's own screen. Questions: does blink/pulse keep the pad's
colour, how many brightness steps does the panel actually resolve, which buttons have real RGB,
and how many characters a cell really shows (`kMaxTextLength` is 50, but that is a protocol cap).

### 3. `0x13`

The display / button-light ownership counterpart to `0x14`. Untested because judging it needs
eyes on the panel rather than a message count.

### 4. Then: the C++ core

The point of all this. `core/` is empty. Port the verified map into a portable library — RtMidi
transport, no JUCE dependency in the core so JUCE, Rust (via C ABI) and CLI tools can all consume
it. Mirror PreSonus's own dirty-tracking `ScreenBuffer`, which only emits SysEx for cells that
actually changed. `probe/demo.py` is the reference integration to reproduce.

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
