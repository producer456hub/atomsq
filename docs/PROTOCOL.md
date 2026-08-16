# PreSonus ATOM SQ — Protocol Reference

Everything we know about how the ATOM SQ talks, written from the standpoint of owning the
device end to end rather than scripting a DAW.

**Provenance matters here.** Each fact below is tagged:

- **[V]** — read directly out of PreSonus's own shipped source (`vendor/presonus-js/`) or
  observed from live USB enumeration. Authoritative.
- **[C]** — from a community reverse-engineering effort. Credible, not yet confirmed on hardware.
- **[?]** — inferred or assumed. Must be proven by a probe before it is relied on.

Unit under test: serial `ATSC20100175`, `bcdDevice 0x0117`.

---

## 1. USB

**[V]** From live `Get-PnpDevice` enumeration on MAINTOP:

| Property | Value |
|---|---|
| Vendor ID | `0x194F` (PreSonus Audio Electronics) |
| Product ID | `0x020A` |
| Device release | `0x0117` |
| Serial | `ATSC20100175` |
| Product string | `ATM SQ` |

It is a **USB composite device** with two functions:

| Interface | Class / SubClass / Protocol | Meaning | Windows driver |
|---|---|---|---|
| MI_00 | `0x01 / 0x01 / 0x00` | USB Audio Class 1 — the MIDI endpoint | `usbaudio`, bound, working |
| MI_02 | `0xFE / 0x01 / 0x01` | **USB DFU, runtime descriptor** | none (Code 28) |

Two consequences:

1. The MIDI side is fully class-compliant. No driver, no vendor SDK, no Universal Control
   required to talk to it — any MIDI API on any OS can drive everything in this document.
2. Firmware update is **standard USB DFU 1.1**, not a proprietary channel. `dfu-util` speaks it
   once a WinUSB/libusb driver is bound on Windows, or natively on Linux. See `FIRMWARE.md`.

`Prot_01` specifically means *runtime* DFU: the device is advertising that it can be asked to
detach into DFU mode. It is not currently in DFU mode.

---

## 2. Entering native mode

**[V]** `vendor/presonus-js/Shared/ATOMCommonMidiDevice.js`

The device boots into a standalone MIDI-controller personality. To take control of the LEDs and
screen, the host claims it:

```
8F 00 7F     Note Off, channel 16, note 0, velocity 127   -> native mode ON
8F 00 00     Note Off, channel 16, note 0, velocity 0     -> native mode OFF
```

Studio One sends the ON message from `onMidiOutConnected()` and the OFF message from `onExit()`.
**Always send the OFF message when releasing the device**, or it is left in a state where it
expects a host that is no longer there.

**[C]** Two further commands appear in the community Bitwig extension and in no PreSonus source:

```
F0 00 01 06 22 13 00/01 F7     display / button-light ownership
F0 00 01 06 22 14 00/01 F7     nav-key capture: 01 = host owns them, 00 = they emit MIDI
```

The extension's author notes `13 01` "alone turns on the lights" and `14 01` "makes the Inst menu
come back to life". These are the most interesting unknowns in the protocol — see
`probe/modes.py`.

---

## 3. Screen

**[V]** `vendor/presonus-js/ATOM SQ/ATOMSQProtocol.js`

```
F0 00 01 06 22 12 <cell> <r> <g> <b> <align> <ascii…> F7
   \_______/  \/    \/    \_____/     \/       \_____/
   PreSonus   ATOM  0x12  7-bit RGB   0|1|2    ≤50 chars
   mfr ID     SQ    write per cell
```

- Manufacturer ID `00 01 06` is PreSonus's; `0x22` selects the ATOM SQ; `0x12` is *write text cell*.
- **14 cells** (`ScreenConfig.kCellCount`), **50 characters max** (`kMaxTextLength`).
- Colour is **per cell**, 7-bit per channel (`0x00`–`0x7F`).
- Alignment: `0` = center, `1` = left, `2` = right.

### Cell layout

**[V]** Confirmed on hardware — writing each cell's own id into it and reading the panel matched
this table exactly. Studio One's device-panel artwork agrees structurally too: three soft-button
columns above, two wide lines through the middle, three columns below.

The screen has six soft buttons, each with two lines, plus two full-width main lines —
6 × 2 + 2 = **14**, which is exactly `kCellCount`:

| | line 1 | line 2 |
|---|---|---|
| soft button 1 | `0x00` | `0x03` |
| soft button 2 | `0x01` | `0x04` |
| soft button 3 | `0x02` | `0x05` |
| **main line 1** | `0x06` | |
| **main line 2** | `0x07` | |
| soft button 4 | `0x08` | `0x0B` |
| soft button 5 | `0x09` | `0x0C` |
| soft button 6 | `0x0A` | `0x0D` |

The soft buttons are the six `lcdButton[0..5]` controls at CC `0x24`–`0x29` (§4), so cell ids
group 0–2 / 8–10 against buttons 1–3 / 4–6. Verify against the panel with `probe/screen.py`.

### Private icon font

**[V]** Control characters in the text payload render as glyphs, not as text. This is how
PreSonus draws arrows and status marks without a bitmap path:

| code | glyph | code | glyph |
|---|---|---|---|
| `0x01` | arrows up/down | `0x09` | degree |
| `0x02` | arrow up | `0x0A` | folder |
| `0x03` | arrow down | `0x0B` | note |
| `0x04` | arrow left | `0x1B` | power |
| `0x05` | arrow right | `0x1C` | ok / check |
| `0x06` | double arrow left | `0x1D` | close / X |
| `0x07` | double arrow right | `0x1E` | dot small |
| `0x08` | circle | `0x1F` | dot big |

### No bitmap path

**[?]** The PreSonus SDK exposes only text cells — there is no graphics primitive anywhere in
the shipped JS. Arbitrary pixel output is therefore probably impossible, the same conclusion the
Xencelabs Quick Keys investigation reached. `probe/modes.py`'s command-id scan is the one
remaining chance to disprove this.

### Efficiency note

**[V]** Studio One keeps a 14-entry `ScreenBuffer` and only emits SysEx for cells whose text,
colour or alignment actually changed. Worth copying — see `core/`.

---

## 4. Control map

**[V]** Extracted mechanically from `vendor/presonus-js/ATOM SQ/ATOM SQ.surface.xml` by
`probe/parse_surface.py`; the full 296-entry table is in `CONTROL_MAP.md`. Everything the device
**sends** is on **channel 1** — CC (`0xB0`) or Note (`0x90`).

### Buttons — CC on channel 1

| CC | control |
|---|---|
| `0x00`–`0x07` | function buttons **A–H** |
| `0x1F` | Shift |
| `0x20` | Song mode |
| `0x21` | Inst mode |
| `0x22` | Editor mode |
| `0x23` | User mode |
| `0x24`–`0x29` | screen soft buttons 1–6 |
| `0x2A` / `0x2B` | wheel left / wheel right |
| `0x40` | sustain touch |
| `0x57` | arrow up |
| `0x59` | arrow down |
| `0x5A` | arrow left |
| `0x66` | arrow right |
| `0x69` | metronome |
| `0x6B` | record |
| `0x6D` | play |
| `0x6F` | stop |

The arrow and transport addresses are deliberately non-contiguous — they sit on Mackie-ish
addresses, which is a hint the firmware shares a control table with other PreSonus surfaces.

### Encoders — relative, CC on channel 1

| CC | control |
|---|---|
| `0x0E`–`0x15` | knobs 1–8 |
| `0x1D` | big wheel |

**[V]** All nine are declared `type="relative" options="signed plain"`. **[?]** In PreSonus's
surface dialect "signed plain" means sign-magnitude around `0x40`: values `0x01`–`0x3F` are
positive deltas, `0x41`–`0x7F` negative. Confirm empirically before trusting it — the alternative
reading is two's complement, and the two disagree on direction.

### Pads

| | |
|---|---|
| Note range | `0x24`–`0x43` (36–67), 32 pads |
| Layout in XML | `pad[0][0..15]` = `0x24`–`0x33`, `pad[1][0..15]` = `0x34`–`0x43` |
| Velocity | note velocity |
| Per-pad pressure | poly aftertouch |
| Global pressure | CC `0x16` |

### ± function pads

**[V]** Notes `0x00` (plus) and `0x01` (minus) for the trigger, and they report continuous
pressure as **poly aftertouch on pitches 0 and 1** — `PadPolyPressureHandler` maps them into a
bipolar wheel value.

### Touch strip

**[V]** Input is **14-bit pitch bend**. Eight modes (`TouchStripMode`): Pitch Bend, Mod Wheel,
Control Link, Expression, Breath Control, Note Repeat, Channel Volume, Channel Pan — default is
Mod Wheel. In Note Repeat mode the firmware value is bucketed into 8 division steps.

---

## 5. LEDs

**[V]** `vendor/presonus-js/Shared/ATOMCommonProtocol.js` + `ATOMCommonMidiDevice.js`

### Pads

State — **Note On, channel 1** (`0x90`), address = the pad's note:

| value | meaning |
|---|---|
| `0x00` | off |
| `0x7F` | on |
| `0x01` | blink |
| `0x02` | pulse |

Colour — the **status channel selects the colour component**, same note address:

| status | component |
|---|---|
| `0x91` | red |
| `0x92` | green |
| `0x93` | blue |

Each component is 7-bit. Studio One white-balances before sending — it scales green by `0.8` and
blue by `0.7` — which implies the physical LEDs are green/blue biased.

### Buttons

**[V]** Identical trick on CC status: `0xB1` / `0xB2` / `0xB3` = R / G / B, address = the
button's CC number from §4. Monochrome on/off is plain `0xB0` at the same address.

### Touch strip

**[V]** 25 discrete LEDs at **CC `55`–`79`** (`0x37`–`0x4F`), value `0` or `127`.
Two rendering modes in the SDK: `MultiLEDHandler` lights everything up to the value (a meter) and
`SingleLEDHandler` lights exactly one (a cursor).

---

## 6. Identity / firmware version

**[V]** Standard universal identity request:

```
-> F0 7E 7F 06 01 F7
<- F0 7E 7F 06 02 …                (17 bytes)
```

Firmware **major** is at `data[13]`, **minor** at `data[14]`, and PreSonus parses them as
`parseInt(byte.toString(16))` — i.e. the bytes are **BCD**, so `0x17` means version 1.7, not 23.
The `bcdDevice` of `0x0117` in the USB descriptor agrees with this reading.

---

## 7. Open questions

1. `0x13` / `0x14` semantics, and whether other command ids exist in `0x10`–`0x1F`. **[C]**
2. Encoder delta encoding — sign-magnitude vs two's complement. **[?]**
3. Whether blink/pulse compose with an assigned colour or override it. **[?]**
4. Real colour bit depth — 7 bits are sent, but the panel may quantise far below that. **[?]**
5. Which buttons actually have RGB LEDs versus plain on/off. **[?]**
6. Real per-cell character capacity. `kMaxTextLength` is 50, but that is a protocol cap, not
   proof the panel can display 50 characters in a soft-button cell. **[?]**
7. DFU: is *upload* (device → host firmware dump) permitted by `bmAttributes`? **[?]**

`probe/screen.py len`, `probe/leds.py compose`, `probe/leds.py depth` and `probe/leds.py buttons`
exist to close 3–6.

---

## Sources

- `vendor/presonus-js/` — PreSonus's shipped ATOM SQ control-surface implementation, copied from
  `C:\Program Files\PreSonus\Studio One 7\devices\PreSonus\ATOM\`. Primary source.
- Live USB enumeration of the connected unit.
- [`JamesB-VS/AtomSQ_Bitwig`](https://github.com/JamesB-VS/AtomSQ_Bitwig) — GPLv3 community Bitwig
  extension; origin of the `0x13`/`0x14` commands and the cell-id table.
- [ATOM SQ Owner's Manual](https://pae-web.presonusmusic.com/downloads/products/pdf/ATOM_SQ_Owners_Manual_V4_EN.pdf)
  — feature-level only; contains no MIDI implementation chart.
