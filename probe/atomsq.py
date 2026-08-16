#!/usr/bin/env python3
"""ATOM SQ low-level driver — shared by every probe script.

Constants here are transcribed from PreSonus's own shipped implementation
(see ../docs/PROTOCOL.md for provenance of each one). Anything still unproven
on hardware is marked UNVERIFIED in a comment so a probe can settle it.

Transport is python-rtmidi directly; mido is not required.
"""

from __future__ import annotations

import sys
import time

import rtmidi

# --------------------------------------------------------------------------
# Ports
# --------------------------------------------------------------------------

# PreSonus's own ATOM SQ.device names this as detectorPortName, so it is the
# control/native-mode port. The second pair (MIDIIN2/MIDIOUT2) is the plain
# MIDI-mode port.
PORT_NAME = "ATM SQ"

# --------------------------------------------------------------------------
# MIDI status bytes
# --------------------------------------------------------------------------

NOTE_OFF = 0x80
NOTE_ON = 0x90
POLY_AT = 0xA0
CC = 0xB0
PITCH_BEND = 0xE0

# --------------------------------------------------------------------------
# Native mode — ATOMCommonMidiDevice.js
# --------------------------------------------------------------------------

NATIVE_ON = [NOTE_OFF | 15, 0x00, 0x7F]
NATIVE_OFF = [NOTE_OFF | 15, 0x00, 0x00]

# --------------------------------------------------------------------------
# SysEx — ATOMSQProtocol.js
# --------------------------------------------------------------------------

SYSEX_START = 0xF0
SYSEX_END = 0xF7

PRESONUS_ID = [0x00, 0x01, 0x06]
ATOMSQ_ID = 0x22
SYSEX_HEADER = [SYSEX_START] + PRESONUS_ID + [ATOMSQ_ID]

CMD_SCREEN_WRITE = 0x12
# UNVERIFIED — community-sourced, not present in PreSonus's own code.
CMD_UNKNOWN_13 = 0x13
CMD_UNKNOWN_14 = 0x14

IDENTITY_REQUEST = [0xF0, 0x7E, 0x7F, 0x06, 0x01, 0xF7]

# --------------------------------------------------------------------------
# Screen — ScreenConfig
# --------------------------------------------------------------------------

CELL_COUNT = 14
MAX_TEXT_LENGTH = 50

ALIGN_CENTER = 0
ALIGN_LEFT = 1
ALIGN_RIGHT = 2

# UNVERIFIED cell layout — from the community Bitwig extension. 6 soft buttons
# x 2 lines + 2 main lines = 14, which at least matches kCellCount exactly.
CELLS = {
    "b1l1": 0x0, "b2l1": 0x1, "b3l1": 0x2,
    "b1l2": 0x3, "b2l2": 0x4, "b3l2": 0x5,
    "main1": 0x6, "main2": 0x7,
    "b4l1": 0x8, "b5l1": 0x9, "b6l1": 0xA,
    "b4l2": 0xB, "b5l2": 0xC, "b6l2": 0xD,
}

# Private icon font: control codes render as glyphs, not text.
ICONS = {
    "arrows_up_down": 0x01, "arrow_up": 0x02, "arrow_down": 0x03,
    "arrow_left": 0x04, "arrow_right": 0x05,
    "arrow_double_left": 0x06, "arrow_double_right": 0x07,
    "circle": 0x08, "degree": 0x09, "folder": 0x0A, "note": 0x0B,
    "power": 0x1B, "ok": 0x1C, "close": 0x1D,
    "dot_small": 0x1E, "dot_big": 0x1F,
}

# --------------------------------------------------------------------------
# Pads / buttons / strip — ATOMCommonProtocol.js, surface.xml
# --------------------------------------------------------------------------

PAD_NOTE_START = 0x24
PAD_COUNT = 32

PAD_LED_OFF = 0x00
PAD_LED_ON = 0x7F
PAD_LED_BLINK = 0x01
PAD_LED_PULSE = 0x02

# The colour component is selected by the status channel, not by the data.
RGB_CHANNEL_R = 1
RGB_CHANNEL_G = 2
RGB_CHANNEL_B = 3

STRIP_LED_START = 55
STRIP_LED_COUNT = 25

# Buttons, by CC address on channel 1 (from surface.xml).
BUTTONS = {
    "A": 0x00, "B": 0x01, "C": 0x02, "D": 0x03,
    "E": 0x04, "F": 0x05, "G": 0x06, "H": 0x07,
    "shift": 0x1F,
    "song": 0x20, "inst": 0x21, "editor": 0x22, "user": 0x23,
    "lcd1": 0x24, "lcd2": 0x25, "lcd3": 0x26,
    "lcd4": 0x27, "lcd5": 0x28, "lcd6": 0x29,
    "wheel_left": 0x2A, "wheel_right": 0x2B,
    "sustain_touch": 0x40,
    "up": 0x57, "down": 0x59, "left": 0x5A, "right": 0x66,
    "metronome": 0x69, "record": 0x6B, "play": 0x6D, "stop": 0x6F,
}

# Relative encoders, by CC address.
ENCODERS = {f"knob{i + 1}": 0x0E + i for i in range(8)}
ENCODERS["wheel"] = 0x1D

PAD_PRESSURE_CC = 0x16
FUNC_PAD_PLUS = 0x00
FUNC_PAD_MINUS = 0x01


def decode_relative(value: int) -> int:
    """Decode a 'signed plain' encoder delta.

    UNVERIFIED reading: sign-magnitude around 0x40 — 0x01..0x3F positive,
    0x41..0x7F negative. probe/encoders.py exists to confirm or refute this.
    """
    if value == 0:
        return 0
    if value < 0x40:
        return value
    return -(value - 0x40)


def clamp7(value: int) -> int:
    return max(0, min(0x7F, int(value)))


def rgb7(r: int, g: int, b: int) -> tuple[int, int, int]:
    """Clamp an RGB triple into the 7-bit range the device uses."""
    return clamp7(r), clamp7(g), clamp7(b)


def rgb_from_8bit(r: int, g: int, b: int) -> tuple[int, int, int]:
    """Convert conventional 0-255 RGB to the device's 0-127 range."""
    return clamp7(r >> 1), clamp7(g >> 1), clamp7(b >> 1)


SIM_HOST = "127.0.0.1"
SIM_PORT = 9001


class SimLink:
    """UDP link to the GUI simulator — one raw MIDI message per datagram."""

    def __init__(self, host: str = SIM_HOST, port: int = SIM_PORT):
        import socket
        self.addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(0.0)

    def send(self, message) -> None:
        try:
            self.sock.sendto(bytes(message), self.addr)
        except OSError:
            pass

    def poll(self):
        """Yield input events the simulator sent back (clicks, knob turns)."""
        while True:
            try:
                data, _addr = self.sock.recvfrom(256)
            except (BlockingIOError, OSError):
                return
            yield 0.0, list(data)

    def close(self) -> None:
        self.sock.close()


class AtomSQ:
    """Open the ATOM SQ's control port and drive it.

    Use as a context manager — native mode is released on exit even if the body
    raises, which matters because a device left in native mode with no host is
    unresponsive until replugged.

    `target` selects where messages go:
      "hw"   real hardware only (default)
      "sim"  the GUI simulator only — no hardware needed
      "both" mirror to both, which is how the sim earns its keep as a
             visualiser: what you see is exactly what the device received.
    """

    def __init__(self, port_name: str = PORT_NAME, native: bool = True,
                 verbose: bool = True, target: str = "hw",
                 sim_port: int = SIM_PORT):
        if target not in ("hw", "sim", "both"):
            raise ValueError(f"target must be hw|sim|both, got {target!r}")
        self.port_name = port_name
        self.want_native = native
        self.verbose = verbose
        self.target = target
        self.use_hw = target in ("hw", "both")
        self.sim = SimLink(port=sim_port) if target in ("sim", "both") else None
        self.midi_in = None
        self.midi_out = None
        if self.use_hw:
            self.midi_in = rtmidi.MidiIn()
            self.midi_out = rtmidi.MidiOut()
            self._in_index = self._find_port(self.midi_in, port_name)
            self._out_index = self._find_port(self.midi_out, port_name)

    @staticmethod
    def _find_port(midi, name: str) -> int:
        ports = midi.get_ports()
        for index, port in enumerate(ports):
            # Windows decorates port names with an index suffix, and the second
            # interface is prefixed MIDIIN2/MIDIOUT2 — match the bare name only.
            if port.startswith(name):
                return index
        raise RuntimeError(
            f"port starting with {name!r} not found. available: {ports}")

    # -- lifecycle ---------------------------------------------------------

    def open(self) -> "AtomSQ":
        if self.use_hw:
            self.midi_in.open_port(self._in_index)
            # SysEx is filtered out by default; we need identity replies.
            self.midi_in.ignore_types(sysex=False, timing=True,
                                      active_sense=True)
            self.midi_out.open_port(self._out_index)
        if self.want_native:
            self.set_native(True)
        return self

    def close(self) -> None:
        try:
            if self.want_native:
                self.set_native(False)
        finally:
            if self.use_hw:
                if self.midi_in.is_port_open():
                    self.midi_in.close_port()
                if self.midi_out.is_port_open():
                    self.midi_out.close_port()
            if self.sim:
                self.sim.close()

    def __enter__(self) -> "AtomSQ":
        return self.open()

    def __exit__(self, *exc) -> None:
        self.close()

    # -- raw send ----------------------------------------------------------

    def send(self, message) -> None:
        message = list(message)
        if self.use_hw:
            self.midi_out.send_message(message)
        if self.sim:
            self.sim.send(message)

    def set_native(self, on: bool) -> None:
        self.send(NATIVE_ON if on else NATIVE_OFF)
        if self.verbose:
            print(f"[native mode {'ON' if on else 'OFF'}]")

    # -- screen ------------------------------------------------------------

    def screen(self, cell: int, text: str, rgb=(0x7F, 0x7F, 0x7F),
               align: int = ALIGN_CENTER) -> None:
        """Write one text cell. Text is ASCII; control codes render as icons."""
        if not 0 <= cell < CELL_COUNT:
            raise ValueError(f"cell must be 0..{CELL_COUNT - 1}, got {cell}")
        r, g, b = rgb7(*rgb)
        payload = [c & 0x7F for c in text.encode("ascii", "replace")]
        if len(payload) > MAX_TEXT_LENGTH:
            payload = payload[:MAX_TEXT_LENGTH]
        self.send(SYSEX_HEADER + [CMD_SCREEN_WRITE, cell, r, g, b, align]
                  + payload + [SYSEX_END])

    def screen_clear(self) -> None:
        for cell in range(CELL_COUNT):
            self.screen(cell, "")

    # -- pads --------------------------------------------------------------

    def pad_state(self, index: int, value: int = PAD_LED_ON) -> None:
        self.send([NOTE_ON, PAD_NOTE_START + index, value])

    def pad_color(self, index: int, rgb) -> None:
        note = PAD_NOTE_START + index
        r, g, b = rgb7(*rgb)
        self.send([NOTE_ON | RGB_CHANNEL_R, note, r])
        self.send([NOTE_ON | RGB_CHANNEL_G, note, g])
        self.send([NOTE_ON | RGB_CHANNEL_B, note, b])

    def pads_off(self) -> None:
        for index in range(PAD_COUNT):
            self.pad_state(index, PAD_LED_OFF)

    # -- buttons -----------------------------------------------------------

    def button_led(self, cc: int, value: int) -> None:
        self.send([CC, cc, clamp7(value)])

    def button_color(self, cc: int, rgb) -> None:
        r, g, b = rgb7(*rgb)
        self.send([CC | RGB_CHANNEL_R, cc, r])
        self.send([CC | RGB_CHANNEL_G, cc, g])
        self.send([CC | RGB_CHANNEL_B, cc, b])

    def buttons_off(self) -> None:
        for cc in BUTTONS.values():
            self.button_led(cc, 0)

    # -- touch strip -------------------------------------------------------

    def strip_leds(self, states) -> None:
        """states: iterable of 25 truthy/falsy values, bottom to top."""
        for index, on in enumerate(states):
            if index >= STRIP_LED_COUNT:
                break
            self.send([CC, STRIP_LED_START + index, 127 if on else 0])

    def strip_meter(self, value: float) -> None:
        """Light every LED up to `value` (0.0-1.0), like MultiLEDHandler."""
        top = int((STRIP_LED_COUNT - 1) * max(0.0, min(1.0, value)))
        self.strip_leds(i <= top for i in range(STRIP_LED_COUNT))

    def strip_off(self) -> None:
        self.strip_leds([False] * STRIP_LED_COUNT)

    # -- input -------------------------------------------------------------

    def poll(self):
        """Yield (delta_time, message) for everything queued, then stop.

        Covers both sources, so a probe reads hardware and simulator input
        through the same loop.
        """
        if self.use_hw:
            while True:
                item = self.midi_in.get_message()
                if item is None:
                    break
                message, delta = item
                yield delta, message
        if self.sim:
            yield from self.sim.poll()

    def identity(self, timeout: float = 1.0):
        """Send an identity request and return the reply bytes, or None."""
        # Drain anything already queued so we do not mistake it for the reply.
        list(self.poll())
        self.send(IDENTITY_REQUEST)
        deadline = time.time() + timeout
        while time.time() < deadline:
            for _delta, message in self.poll():
                if len(message) >= 5 and message[:5] == [0xF0, 0x7E, 0x7F, 0x06, 0x02]:
                    return message
            time.sleep(0.01)
        return None

    def blackout(self) -> None:
        """Everything off — safe state to leave the device in."""
        self.pads_off()
        self.buttons_off()
        self.strip_off()
        self.screen_clear()


def target_from_argv(argv=None) -> str:
    """Extract `--target hw|sim|both` from argv, removing it in place.

    Probe scripts use plain positional args, so rather than give each one an
    argparse setup we strip this single shared flag here. Falls back to the
    ATOMSQ_TARGET environment variable, then "hw".
    """
    import os
    if argv is None:
        argv = sys.argv
    target = os.environ.get("ATOMSQ_TARGET", "hw")
    if "--target" in argv:
        index = argv.index("--target")
        if index + 1 < len(argv):
            target = argv[index + 1]
            del argv[index:index + 2]
        else:
            del argv[index]
    for flag, value in (("--sim", "sim"), ("--both", "both")):
        if flag in argv:
            argv.remove(flag)
            target = value
    return target


def describe(message) -> str:
    """Human-readable one-liner for a raw MIDI message."""
    if not message:
        return "(empty)"
    status = message[0]
    if status == SYSEX_START:
        return "SysEx " + " ".join(f"{b:02X}" for b in message)
    kind, channel = status & 0xF0, (status & 0x0F) + 1
    data = message[1:]
    names = {NOTE_OFF: "NoteOff", NOTE_ON: "NoteOn", POLY_AT: "PolyAT",
             CC: "CC", PITCH_BEND: "PitchBend"}
    name = names.get(kind, f"0x{kind:02X}")
    if kind == PITCH_BEND and len(data) >= 2:
        return f"{name} ch{channel} value={data[0] | (data[1] << 7)}"
    body = " ".join(f"{b:3d}" for b in data)
    return f"{name} ch{channel} {body}"
