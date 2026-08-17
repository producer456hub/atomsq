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

### DFU functional descriptor

**[V]** Read on Linux (surfpad) with `lsusb -v -d 194f:020a` — no driver binding, no `dfu-util`:

```
Device Firmware Upgrade Interface Descriptor:
  bmAttributes                       0x0B
    Will Detach
    Manifestation Intolerant
    Upload Supported
    Download Supported
  wDetachTimeout                    255 milliseconds
  wTransferSize                      64 bytes
  bcdDFUVersion                   1.10
```

The headline is **Upload Supported** — the device will dump its own firmware to the host, so the
image can be obtained from the unit itself rather than reverse-engineered out of a Universal
Control installer. `Will Detach` means it detaches itself on `DFU_DETACH` without the host
forcing a USB reset. `Manifestation Intolerant` means it expects a bus reset after a download
completes.

**Not yet attempted.** Reading this descriptor is passive; *detaching into DFU mode* is a real
state change and is gated on an explicit decision.

### Full device descriptor

**[V]** `bcdUSB 2.00`, full speed (12 Mbps), bus powered, `MaxPower 500 mA`, `bcdDevice 1.17`,
`iManufacturer` "PreSonus", `iProduct` "ATM SQ", `iSerial` "ATSC20100175". Three interfaces:
0 = Audio Control, 1 = MIDI Streaming (two embedded in-jacks and two out-jacks, bulk endpoints
`0x02` OUT / `0x81` IN, 64-byte packets), 2 = DFU.

---

## 1a. The two MIDI ports

**[V]** The MIDI Streaming interface exposes **two embedded jack pairs**, so the device presents
two independent port pairs. Their real names come from the USB string descriptors, which Linux
surfaces verbatim (Windows renames the second one to `MIDIIN2/MIDIOUT2`):

| ALSA | name | Windows | behaviour |
|---|---|---|---|
| `hw:1,0,0` | **ATM SQ** | `ATM SQ` | The control/native port. Answers the identity request, carries all panel traffic (knob CCs observed here), and is what PreSonus's `.device` file names as `detectorPortName`. |
| `hw:1,0,1` | **ATM SQ Control** | `MIDIIN2 (ATM SQ)` | **Silent.** No unsolicited traffic, does not answer the universal identity request, and emits nothing while the panel is exercised — in any mode. |

**[V]** Tested properly with `probe/ports.py`: both ports opened at once for two minutes while
every control was exercised — pads, knobs, touch strip, buttons — and repeated after switching
through Song, Inst, Editor and User. Result: **199 messages on port 1, zero on port 2.** It
carries no panel data under any mode, so it is not a duplicate stream, a thru, or a
mode-dependent split.

The naming is counter-intuitive: the port *called* "Control" is the quiet one, while the plainly
named port carries the control protocol. The likely explanation is that `hw:1,0,1` is the channel
PreSonus's own Universal Control / Control Editor uses to read and write the device's stored
configuration (the user-mode remapping), and that it only answers vendor-specific requests we
have not yet found. **[?]**

Note when testing this: `amidi -p PORT -S ... -d` races its own reply — the send completes before
the dump starts listening, so the answer is lost. Start the listener first, then send.

**[V] macOS names the ports exactly as Linux does** — `ATM SQ` and `ATM SQ Control`, confirmed
with `probe/identity.py` on macOS 26 (Apple silicon). Windows' `MIDIIN2 (ATM SQ)` renaming is a
Windows behaviour, not the device's, so `port.startswith("ATM SQ")` works unchanged on macOS.
The whole Python probe rig runs there too, with `python-rtmidi` in a venv — previously this had
only ever run on Windows and Linux.

⚠️ **iOS/iPadOS remains unrecorded, and must not be inferred from macOS.** On iPad a Novation
Launchkey has been seen enumerating as "DAW Out/In" with no vendor name at all.

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
come back to life".

**[V]** All four messages were sent to the unit and it answered **nothing** to any of them, so
they are write-only state flags — which is what a mode switch should look like. The device
accepted them without complaint and continued to operate normally afterwards.

### `0x14` — nav-key capture — CONFIRMED

**[V]** A/B-tested on hardware with `probe/modes.py navkeys`, counting messages per phase:

| phase | flag | nav-key messages | other messages |
|---|---|---|---|
| A | `14 00` | **7** | 0 |
| B | `14 01` | **0** | **19** |

The 19 other messages in phase B are what make this conclusive: the device was still transmitting,
so the nav keys went silent specifically rather than the device dropping off. A null result caused
by a disconnect would have shown zero of everything.

```
F0 00 01 06 22 14 01 F7    host owns the nav keys — they stop emitting MIDI
F0 00 01 06 22 14 00 F7    nav keys emit MIDI normally
```

This is how a host takes over the arrow cluster for its own navigation without those keys also
firing MIDI at the DAW.

`0x13` — the display / button-light ownership counterpart — remains **[?]**. It is harder to test
objectively because judging it needs eyes on the panel.

**Not scanned:** the rest of the command-id space. This device exposes a USB DFU interface, so an
unknown command id could plausibly detach it into the bootloader. Sweeping `0x00`–`0x7F` is a
deliberate decision to be taken explicitly, not a thing to do casually.

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

### Real text capacity, and automatic ellipsis

**[V]** `kMaxTextLength = 50` is what the *message* accepts, not what the panel *shows*. Measured
by writing a 49-glyph ruler (`A`–`Z` then `a`–`w`, so the last readable letter gives an exact
count) into a wide line and a soft cell:

| cell | characters shown | overflow |
|---|---|---|
| **main line** (full width) | last readable letter `Y` = **25**, plus the ellipsis → **26 cells** | device appends `…` |
| **soft-button cell** (one of three columns) | last readable letter `G` = **7**, plus the ellipsis → **8 cells** | device appends `…` |

Two things worth knowing:

- **The device truncates for you, and marks it.** Overflow is not silently clipped — it renders a
  single ellipsis **glyph occupying one character cell** (not three dots). So overflow is always
  visible to the user rather than invisibly lost.
- The geometry is self-consistent: three soft columns at 8 cells each is 24, against 26 on the
  full-width line.

For `core/`: truncate at **25** (main) and **7** (soft) when you want to control what gets
dropped — abbreviate meaningfully rather than letting the tail disappear. Send longer text only
when an ellipsis is an acceptable outcome.

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

### Buttons send a press AND a release

**[V] Confirmed on hardware** — `probe/hold.py`, macOS, native mode. Every button tested sent
`127` on press and `0` on release:

| button | CC | observed |
|---|---|---|
| shift | `0x1F` | `127, 0` |
| A | `0x00` | `127, 0` |
| lcd1 (soft key 1) | `0x24` | `127, 0` |
| song | `0x20` | `127, 0` |
| play | `0x6D` | `127, 0` |
| up (arrow) | `0x57` | `127, 0` |

One from each family — modifier, function row, soft key, mode column, transport, navigation —
because the transport and arrow addresses are Mackie-ish and could plausibly have been wired
differently.

This matters more than it looks. `surface.xml` declares these as transmitting CC and says
nothing whatever about what a release looks like, so a host wanting **"hold X, press Y"**
combinations had no documented basis for the release edge. It has one now: the modifier is
**held, not toggled**.

Not tested individually: `B`–`H`, `lcd2`–`lcd6`, `inst`, `editor`, `user`, `wheel_left`,
`wheel_right`, `sustain_touch`, `down`, `left`, `right`, `metronome`, `record`, `stop`. Six of
six across every family is strong evidence the panel is uniform, but it is evidence, not a
sweep — `probe/hold.py --all` walks the lot.

### Encoders — relative, CC on channel 1

| CC | control |
|---|---|
| `0x0E`–`0x15` | knobs 1–8 |
| `0x1D` | big wheel |

**[V]** All nine are declared `type="relative" options="signed plain"`.

### The acceleration curve is real

**[V]** Observed on hardware. The CC value is a **speed-weighted magnitude**, not a tick count —
this is the "velocity multiplier" the manual mentions. One continuous turn of knob 4:

```
+1 +2 +7 +12 +17 +22 +27 +32   then   +31 +26 +21 +16 +11 +10 +9 +8
```

It ramps in steps of roughly 5 and decays the same way. The largest magnitude seen so far is
`0x23` (35), on knob 8. A host must treat these as weighted deltas — accumulating them as single
ticks makes fast turns crawl, and scaling them linearly makes slow turns unusable.

### Direction encoding — SIGN-MAGNITUDE around `0x40`

**[V]** Settled on hardware with `probe/encoders.py`, one direction per phase. A slow, steady
turn of knob 1 gave a single value throughout each phase:

| direction | every message |
|---|---|
| clockwise | `0x01` |
| counter-clockwise | `0x41` |

```
v < 0x40   ->  delta = +v
v > 0x40   ->  delta = -(v - 0x40)
```

So `0x01` is +1 and `0x41` is −1; magnitude is the low 6 bits and bit 6 is the sign. This is what
`decode_relative()` in `probe/atomsq.py` already implemented — now verified rather than assumed.

Note the constant value across a whole phase: at a slow, even rotation speed the magnitude stays
at 1 and never accelerates, which is consistent with the speed-weighted curve above. Captured in
native mode; the standalone-mode capture (`08`–`14` under acceleration) agrees in kind, so the
encoding does not change between modes.

### The encoders have no detents

**[V]** Physically confirmed: the eight knobs and the wheel turn smoothly with no click stops, so
there is no such thing as a "tick" to count. That is not a detail — it means the CC value can
*only* be a speed-weighted magnitude, and any host treating these as step counts will feel wrong
no matter how it scales them.

### Pads

| | |
|---|---|
| Note range | `0x24`–`0x43` (36–67), 32 pads |
| Layout in XML | `pad[0][0..15]` = `0x24`–`0x33`, `pad[1][0..15]` = `0x34`–`0x43` |
| Velocity | note velocity |
| Per-pad pressure | poly aftertouch |
| Global pressure | CC `0x16` |

**[V] Pads transmit on MIDI channel 10, not channel 1.** Captured from the device in its default
standalone mode: `99 30 10` / `89 30 00` — Note On/Off on **channel 10** (the GM drum channel),
note `0x30`, i.e. `pad[0][12]`.

This is an asymmetry worth being careful about: pad **LED output** is channel 1 (`0x90`, with
`0x91`/`0x92`/`0x93` carrying colour), but pad **note input** arrives on channel 10.
`surface.xml` hides this by declaring pads with the symbolic status `NoteTrigger` rather than a
literal byte, leaving the channel for Studio One to resolve. Whether native mode changes the
input channel is still **[?]** — worth confirming with `probe/listen.py --native`.

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

**[V] Animation composes with colour.** Confirmed on hardware: with all 32 pads set to different
hues and half blinking, half pulsing, every pad animated **in its own colour** — the rainbow
survived and the two animations were clearly distinguishable. Colour and animation are
independent, so blink and pulse are usable for colour-coded state rather than being mutually
exclusive with it.

That test also **verified the physical row mapping**, until then only inferred from the XML:
blink went to pad indices 0–15 and pulse to 16–31, and the lower row flashed while the upper row
pulsed. So `pad[0][*]` (notes `0x24`–`0x33`) is the **lower** row, `pad[1][*]` (`0x34`–`0x43`) the
upper.

**[V] Brightness is monotonic and smooth.** A red ramp of 0, 4, 8 … 124 across the pads in note
order read as a continuous left-to-right gradient with the upper row brightest, no obvious
banding. The exact step count was not measured, but there is no coarse quantisation — the full
`0x00`–`0x7F` range is usable and fades should look clean.

Colour — the **status channel selects the colour component**, same note address:

| status | component |
|---|---|
| `0x91` | red |
| `0x92` | green |
| `0x93` | blue |

Each component is 7-bit. Studio One white-balances before sending — it scales green by `0.8` and
blue by `0.7` — which implies the physical LEDs are green/blue biased.

### Buttons — only a minority actually take colour

**[V]** The addressing is the same trick on CC status: `0xB1` / `0xB2` / `0xB3` = R / G / B,
address = the button's CC number from §4, with plain `0xB0` as brightness. But **most of the
panel does not honour it.** Established by driving all 30 addressable buttons to pure green, then
blue, then red, then all three channels at once, and reading the panel each time:

| buttons | LED | behaviour |
|---|---|---|
| **A–H** (CC `0x00`–`0x07`) | **full RGB** | took green, blue and red |
| **Play** (CC `0x6D`) | **full RGB** | took green, blue and red |
| **Record** (CC `0x6B`) | **red only** | ignored green and blue |
| **Metronome** (CC `0x69`) | **blue only** | ignored green and red |
| soft buttons `lcd1`–`lcd6`, nav arrows, wheel L/R, Shift, mode column (Song/Inst/Editor/User) | **not ours** | permanently lit **amber**, unaffected by any colour write |

So **nine buttons take colour** (eight of them fully), two are fixed single-colour, and the entire
right-hand cluster is driven by the device's own firmware for its menu UI and never responds to
the host at all.

A library that models all 30 as RGB would be lying about two thirds of them — `core/` must expose
these as distinct kinds.

**Testing note:** asking "which buttons are green" and then repeating for blue and red cannot
detect a fixed-red button — it is lit during every pass and the question never asks about the one
colour it shows. Driving R, G and B together lights everything that can light, in its own colour,
and gives the whole map in one look.

### `0x13` does not hand over the amber cluster

**[V]** Tested: `F0 00 01 06 22 13 01 F7` followed by colour writes to the whole right-hand
cluster left them unchanged — still amber. So the community reading of `0x13` as a
panel-ownership switch does not extend to those LEDs, and there is a **hard ceiling on host
control of this surface** that applies to any software, ours or anyone's.

Caveat on scope: only this ordering was tried (`0x13` first, then colour). It remains possible
that the writes must precede the flag, or that `0x14` must also be set. **[?]**

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

Almost everything is settled. What remains:

1. Whether `0x13` can be made to hand over the amber right-hand cluster under some *other*
   ordering — colour writes before the flag, or `0x14` set as well. As tested, it cannot. **[?]**
2. Exact LED bit depth. The ramp is smooth with no visible banding, so the full range is usable,
   but the true number of steps was not counted. **[?]**
3. What the second MIDI port (`ATM SQ Control`) carries. Silent under every condition tried;
   plausibly the channel Universal Control uses for configuration. **[?]**
4. Firmware. Closed without a disassembly pass — see `FIRMWARE.md`. **[?]**

## Sources

- `vendor/presonus-js/` — PreSonus's shipped ATOM SQ control-surface implementation, copied from
  `C:\Program Files\PreSonus\Studio One 7\devices\PreSonus\ATOM\`. Primary source.
- Live USB enumeration of the connected unit.
- [`JamesB-VS/AtomSQ_Bitwig`](https://github.com/JamesB-VS/AtomSQ_Bitwig) — GPLv3 community Bitwig
  extension; origin of the `0x13`/`0x14` commands and the cell-id table.
- [ATOM SQ Owner's Manual](https://pae-web.presonusmusic.com/downloads/products/pdf/ATOM_SQ_Owners_Manual_V4_EN.pdf)
  — feature-level only; contains no MIDI implementation chart.
