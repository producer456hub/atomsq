# atomsq core

A portable C++17 library for driving the PreSonus ATOM SQ, built against the
hardware-verified protocol in [`../docs/PROTOCOL.md`](../docs/PROTOCOL.md).

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
./build/atomsq_tests
```

## No dependencies in the core

MIDI arrives through a `Transport` interface, so `atomsq_core` links against
nothing. That is deliberate:

- A JUCE app, a DAW, or anything that **already owns a connection** to the
  device can feed the surface directly instead of opening a second one — you
  cannot open the same MIDI port twice on Windows.
- A Rust caller can use it behind a C ABI without inheriting a MIDI backend.
- Every message the library builds is **testable with no hardware present**.

`RtMidiTransport` is an optional adapter, built only when RtMidi is found.

## What the API models

The interesting design work here is refusing to paper over what the hardware
actually does.

**Buttons are not uniform.** Of 30 addressable buttons, only nine take colour.
`ledKind()` reports which of four classes a button is in, and
`setButtonColor()` is a no-op on the ones the firmware owns rather than
emitting bytes the device will ignore:

| class | buttons |
|---|---|
| `Rgb` | A–H, Play |
| `FixedRed` | Record |
| `FixedBlue` | Metronome |
| `FirmwareOwned` | soft buttons, nav cluster, wheel arrows, Shift, mode column, Stop |

Ask `supportsColor()` before designing a colour-coded layout around a button.

**Colour is selected by the status channel**, not by the data — channel 1 is
state, channels 2/3/4 are red/green/blue at the same address. `setPadColor()`
hides that, but it is why a pad takes three messages.

**Encoder deltas are speed-weighted, not tick counts.** The knobs have no
detents, so there is no tick to count; `EncoderEvent::delta` carries the signed
magnitude the device reported and the caller decides how to scale it.
Accumulating them as single steps makes fast turns crawl.

**Screen text is truncated to the real cell width** — 25 characters on a main
line, 7 in a soft cell. Beyond that the device appends its own ellipsis glyph,
so `Screen::fit()` truncates first and lets you choose the abbreviation.

**Cells are dirty-tracked.** `flush()` emits only what changed, and returns how
many cells it wrote. A full 14-cell repaint is a lot of SysEx on a stream
shared with note traffic; PreSonus's own implementation does the same thing.
Cells start dirty, so the first flush after claiming the device paints
everything — the panel's contents are undefined until then.

**Native mode is released in the destructor**, including while unwinding. A
device left claimed with no host is unresponsive until it is replugged.

**Unrecognised input is surfaced**, not swallowed. If `Callbacks::unhandled`
ever fires, the protocol model has a hole in it and that is worth knowing.

## Tests

`tests/test_core.cpp` asserts exact byte sequences against the protocol doc
through a `RecordingTransport` — screen message layout, the channel-per-colour
encoding, pad animation, encoder sign-magnitude decode, pad input arriving on
channel 10 while pad LEDs live on channel 1, dirty-tracking actually
suppressing redundant traffic, and colour writes to firmware-owned buttons
being dropped.

43 checks, no hardware required.

## Status

All four targets build clean on g++ (aarch64, `-Wall -Wextra -Wpedantic`, **no warnings**) with
RtMidi 6.0.0:

```
libatomsq_core.a     the dependency-free core
libatomsq_rtmidi.a   the optional RtMidi adapter
atomsq_tests         43 checks, 0 failures
atomsq_demo          reference integration
```

The demo has not yet been run against the hardware — it needs the unit plugged into the same
machine as the build. Its no-device path is exercised and behaves correctly: it reports which
port prefix it looked for and lists what it did find, rather than failing silently.
