#!/usr/bin/env python3
"""ATOM SQ GUI simulator, drawn on a photo of the real unit.

The background is the official top-down render (extracted from the owner's
manual), and every live element — 32 pads, 14 screen cells, 25 strip LEDs,
every button — is drawn registered to it using `layout.py`. Using the photo as
the substrate means layout compliance is checked by eye continuously: if a
drawn control does not sit on its printed counterpart, the geometry is wrong.

Two jobs:

1. **Visualiser** — decode the exact bytes we send and show what the hardware
   would do. Same parsing the device does, so if the sim looks wrong our bytes
   are wrong. Anything it cannot explain bumps an "unexplained" counter.
2. **Stand-in** — develop with no hardware attached; clicking pads and buttons
   sends real input back to the driving script.

Transport is UDP, one raw MIDI message per datagram, so any language can drive
it.

    python sim/atomsq_sim.py [--port 9001] [--width 1500]

    python probe/screen.py map --target sim
    python probe/leds.py sweep --both

Keys:  c  calibration outlines      g  hide/show the photo
       l  toggle control labels     q  quit
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "probe"))

import layout  # noqa: E402
from atomsq import (  # noqa: E402
    ALIGN_LEFT, ALIGN_RIGHT, ATOMSQ_ID, BUTTONS, CC, CELL_COUNT,
    CMD_SCREEN_WRITE, ENCODERS, ICONS, NOTE_OFF, NOTE_ON, PAD_COUNT,
    PAD_LED_BLINK, PAD_LED_OFF, PAD_LED_PULSE, PAD_NOTE_START, PRESONUS_ID,
    STRIP_LED_COUNT, STRIP_LED_START, SYSEX_START,
)

DEFAULT_PORT = 9001
ASSETS = Path(__file__).resolve().parent / "assets"

BG = "#0e0e10"
INK = "#d8d8dc"
DIM = "#6a6a72"
UNLIT_PAD = "#17171b"
SCREEN_BG = "#03060c"

CC_TO_BUTTON = {cc: name for name, cc in BUTTONS.items()}

# The device renders these control codes as private-font glyphs. Substitute a
# single Unicode character each so a cell occupies the same width here as it
# does on the panel — spelling the names out would misrepresent the layout.
ICON_GLYPHS = {
    ICONS["arrows_up_down"]: "↕",   # up-down arrow
    ICONS["arrow_up"]: "▲",
    ICONS["arrow_down"]: "▼",
    ICONS["arrow_left"]: "◄",
    ICONS["arrow_right"]: "►",
    ICONS["arrow_double_left"]: "«",
    ICONS["arrow_double_right"]: "»",
    ICONS["circle"]: "○",
    ICONS["degree"]: "°",
    ICONS["folder"]: "▤",
    ICONS["note"]: "♪",
    ICONS["power"]: "◉",
    ICONS["ok"]: "✓",
    ICONS["close"]: "✕",
    ICONS["dot_small"]: "·",
    ICONS["dot_big"]: "●",
}


def to_hex_color(r: int, g: int, b: int) -> str:
    """7-bit device RGB -> 8-bit screen hex."""
    return "#%02x%02x%02x" % (min(255, r * 2), min(255, g * 2), min(255, b * 2))


class Cell:
    __slots__ = ("text", "color", "align")

    def __init__(self):
        self.text = ""
        self.color = (0x7F, 0x7F, 0x7F)
        self.align = 0


class Pad:
    __slots__ = ("state", "color")

    def __init__(self):
        self.state = PAD_LED_OFF
        self.color = (0x7F, 0x7F, 0x7F)


class PanelState:
    """Everything the device renders, as the protocol describes it."""

    def __init__(self):
        self.native = False
        self.cells = [Cell() for _ in range(CELL_COUNT)]
        self.pads = [Pad() for _ in range(PAD_COUNT)]
        self.buttons = {}          # cc -> brightness 0..127
        self.button_colors = {}    # cc -> (r, g, b)
        self.strip = [0] * STRIP_LED_COUNT
        self.log = []
        self.unknown = []

    def note(self, line: str) -> None:
        self.log.append(f"{time.strftime('%H:%M:%S')}  {line}")
        del self.log[:-400]


class Decoder:
    """Turn raw MIDI into PanelState changes, using the documented protocol."""

    def __init__(self, state: PanelState):
        self.state = state

    def feed(self, data: bytes) -> None:
        if not data:
            return
        message = list(data)
        if message[0] == SYSEX_START:
            self._sysex(message)
            return
        if len(message) < 3:
            return
        status, addr, value = message[0], message[1], message[2]
        kind, channel = status & 0xF0, status & 0x0F

        # Native mode: Note Off on channel 16, note 0.
        if kind == NOTE_OFF and channel == 15 and addr == 0x00:
            self.state.native = value >= 0x40
            self.state.note(f"native mode {'ON' if self.state.native else 'OFF'}")
            return

        if kind == NOTE_ON:
            self._pad(channel, addr, value)
        elif kind == CC:
            self._cc(channel, addr, value)
        else:
            self.state.unknown.append(message)
            self.state.note(f"unhandled {status:02X} {addr:02X} {value:02X}")

    def _pad(self, channel: int, note: int, value: int) -> None:
        index = note - PAD_NOTE_START
        if not 0 <= index < PAD_COUNT:
            self.state.note(f"note {note:02X} outside pad range")
            self.state.unknown.append([NOTE_ON | channel, note, value])
            return
        pad = self.state.pads[index]
        if channel == 0:
            pad.state = value
        elif channel in (1, 2, 3):
            # The status channel selects which colour component this is.
            r, g, b = pad.color
            pad.color = {1: (value, g, b), 2: (r, value, b),
                         3: (r, g, value)}[channel]
        else:
            self.state.note(f"pad note on unexpected channel {channel + 1}")

    def _cc(self, channel: int, cc: int, value: int) -> None:
        if channel == 0 and STRIP_LED_START <= cc < STRIP_LED_START + STRIP_LED_COUNT:
            self.state.strip[cc - STRIP_LED_START] = value
            return
        if channel == 0:
            self.state.buttons[cc] = value
            return
        if channel in (1, 2, 3):
            r, g, b = self.state.button_colors.get(cc, (0, 0, 0))
            self.state.button_colors[cc] = {
                1: (value, g, b), 2: (r, value, b), 3: (r, g, value)}[channel]
            return
        self.state.note(f"cc on unexpected channel {channel + 1}")

    def _sysex(self, message) -> None:
        body = message[1:-1] if message[-1] == 0xF7 else message[1:]
        if body[:3] != PRESONUS_ID or len(body) < 5 or body[3] != ATOMSQ_ID:
            self.state.note("sysex: not an ATOM SQ message")
            self.state.unknown.append(message)
            return
        command, args = body[4], body[5:]
        if command == CMD_SCREEN_WRITE and len(args) >= 5:
            cell_id, r, g, b, align = args[:5]
            if 0 <= cell_id < CELL_COUNT:
                cell = self.state.cells[cell_id]
                cell.text = "".join(chr(c) for c in args[5:])
                cell.color = (r, g, b)
                cell.align = align
        else:
            # 0x13 / 0x14 land here — exactly what we want surfaced.
            self.state.note(f"sysex cmd 0x{command:02X} args="
                            + " ".join(f"{a:02X}" for a in args))
            self.state.unknown.append(message)


class Server(threading.Thread):
    """UDP listener: one inbound datagram = one raw MIDI message."""

    daemon = True

    def __init__(self, decoder: Decoder, port: int):
        super().__init__()
        self.decoder = decoder
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", port))
        self.port = port
        self.client = None

    def run(self) -> None:
        while True:
            try:
                data, addr = self.sock.recvfrom(4096)
            except OSError:
                return
            self.client = addr
            self.decoder.feed(data)

    def send_input(self, message) -> None:
        if self.client:
            try:
                self.sock.sendto(bytes(message), self.client)
            except OSError:
                pass


class SimulatorUI:
    def __init__(self, root: tk.Tk, state: PanelState, server: Server,
                 width: int):
        self.root = root
        self.state = state
        self.server = server
        self.blink_phase = 0.0
        self.show_photo = True
        self.show_calibration = False
        self.show_labels = False

        self.scale = width / layout.IMAGE_W
        self.height = int(layout.IMAGE_H * self.scale)
        self.photo = self._load_photo(width, self.height)

        root.title(f"ATOM SQ simulator — udp 127.0.0.1:{server.port}")
        root.configure(bg=BG)

        self.canvas = tk.Canvas(root, width=width, height=self.height, bg=BG,
                                highlightthickness=0)
        self.canvas.pack(side=tk.TOP)

        self.logbox = tk.Text(root, height=7, bg="#08080a", fg=DIM,
                              font=("Consolas", 9), highlightthickness=0,
                              borderwidth=0)
        self.logbox.pack(side=tk.BOTTOM, fill=tk.X)

        self.hit_targets = []
        self._pressed = None
        self._hover_encoder = None
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Motion>", self._on_motion)
        root.bind("<Key>", self._on_key)

        self.tick()

    # -- assets -----------------------------------------------------------

    def _load_photo(self, width: int, height: int):
        path = ASSETS / layout.IMAGE
        if not path.exists():
            print(f"panel photo missing: {path}")
            return None
        try:
            from PIL import Image, ImageTk
        except ImportError:
            print("panel photo needs Pillow: pip install pillow")
            return None
        image = Image.open(path).convert("RGB")
        return ImageTk.PhotoImage(image.resize((width, height), Image.LANCZOS))

    # -- coordinate helpers ----------------------------------------------

    def px(self, box):
        """Scale a layout rect into canvas pixels."""
        x0, y0, x1, y1 = box
        s = self.scale
        return x0 * s, y0 * s, x1 * s, y1 * s

    def circle(self, spec):
        cx, cy, r = spec
        s = self.scale
        return (cx - r) * s, (cy - r) * s, (cx + r) * s, (cy + r) * s

    def _register(self, box, on_press=None, on_release=None, encoder=None):
        self.hit_targets.append((box, on_press, on_release, encoder))

    # -- input ------------------------------------------------------------

    def _on_motion(self, event):
        self._hover_encoder = None
        for box, _p, _r, encoder in self.hit_targets:
            x0, y0, x1, y1 = box
            if encoder and x0 <= event.x <= x1 and y0 <= event.y <= y1:
                self._hover_encoder = encoder
                return

    def _on_click(self, event):
        for box, on_press, on_release, _enc in self.hit_targets:
            x0, y0, x1, y1 = box
            if x0 <= event.x <= x1 and y0 <= event.y <= y1:
                if on_press:
                    on_press()
                self._pressed = on_release
                return

    def _on_release(self, _event):
        if self._pressed:
            self._pressed()
            self._pressed = None

    def _on_wheel(self, event):
        if not self._hover_encoder:
            return
        cc = ENCODERS[self._hover_encoder]
        # 'signed plain': 0x01..0x3F positive, 0x41..0x7F negative.
        raw = 1 if event.delta > 0 else 0x41
        self.server.send_input([CC, cc, raw])
        self.state.note(f"-> {self._hover_encoder} "
                        f"{'+1' if event.delta > 0 else '-1'} (CC {cc:02X}={raw:02X})")

    def _on_key(self, event):
        key = event.keysym.lower()
        if key == "c":
            self.show_calibration = not self.show_calibration
        elif key == "g":
            self.show_photo = not self.show_photo
        elif key == "l":
            self.show_labels = not self.show_labels
        elif key == "q":
            self.root.destroy()

    # -- drawing ----------------------------------------------------------

    def tick(self):
        self.blink_phase = (self.blink_phase + 0.08) % 1.0
        self.canvas.delete("all")
        self.hit_targets.clear()

        if self.photo is not None and self.show_photo:
            self.canvas.create_image(0, 0, image=self.photo, anchor="nw")

        self.draw_pads()
        self.draw_function_pads()
        self.draw_screen()
        self.draw_strip()
        self.draw_buttons()
        self.draw_knobs()
        if self.show_calibration:
            self.draw_calibration()
        self.draw_status()
        self.sync_log()
        self.root.after(50, self.tick)

    def draw_pads(self):
        for index in range(PAD_COUNT):
            pad = self.state.pads[index]
            note = PAD_NOTE_START + index
            x0, y0, x1, y1 = self.px(layout.PADS[index])
            fill = UNLIT_PAD
            if pad.state != PAD_LED_OFF:
                r, g, b = pad.color
                visible = True
                if pad.state == PAD_LED_BLINK:
                    visible = self.blink_phase < 0.5
                elif pad.state == PAD_LED_PULSE:
                    dim = 0.35 + 0.65 * abs(0.5 - self.blink_phase) * 2
                    r, g, b = int(r * dim), int(g * dim), int(b * dim)
                fill = to_hex_color(r, g, b) if visible else UNLIT_PAD
            self.canvas.create_rectangle(x0, y0, x1, y1, fill=fill,
                                         outline="#000000", width=1)
            if self.show_labels:
                self.canvas.create_text((x0 + x1) / 2, y1 - 9,
                                        text=f"{note:02X}", fill="#8a8a94",
                                        font=("Consolas", 7))
            self._register(
                (x0, y0, x1, y1),
                on_press=lambda n=note: self._send_note(n, 100),
                on_release=lambda n=note: self._send_note(n, 0))

    def draw_function_pads(self):
        for name, note in (("plus", 0x00), ("minus", 0x01)):
            x0, y0, x1, y1 = self.px(layout.FUNCTION_PADS[name])
            self._register(
                (x0, y0, x1, y1),
                on_press=lambda n=note: self._send_note(n, 100),
                on_release=lambda n=note: self._send_note(n, 0))
            if self.show_calibration:
                self.canvas.create_rectangle(x0, y0, x1, y1, outline="#39d0ff")

    def draw_screen(self):
        x0, y0, x1, y1 = self.px(layout.SCREEN)
        self.canvas.create_rectangle(x0, y0, x1, y1, fill=SCREEN_BG,
                                     outline="#0d1522")
        width, height = x1 - x0, y1 - y0
        col_w = width / 3
        band = height / 3

        # Top band: soft buttons 1-3, line 1 then line 2.
        # Middle band: the two wide main lines.
        # Bottom band: soft buttons 4-6.
        for col, (l1, l2) in enumerate([(0, 3), (1, 4), (2, 5)]):
            cx = x0 + col * col_w
            self._cell(l1, cx, y0 + 2, col_w, band / 2 - 2)
            self._cell(l2, cx, y0 + band / 2, col_w, band / 2 - 2)
            if col:
                self.canvas.create_line(cx, y0, cx, y0 + band, fill="#16233a")

        mid = y0 + band
        self.canvas.create_rectangle(x0, mid, x1, mid + band, fill="#060b14",
                                     outline="#16233a")
        self._cell(6, x0, mid + 3, width, band / 2 - 3, big=True)
        self._cell(7, x0, mid + band / 2, width, band / 2 - 3, big=True)

        low = mid + band
        for col, (l1, l2) in enumerate([(8, 11), (9, 12), (10, 13)]):
            cx = x0 + col * col_w
            self._cell(l1, cx, low + 2, col_w, band / 2 - 2)
            self._cell(l2, cx, low + band / 2, col_w, band / 2 - 2)
            if col:
                self.canvas.create_line(cx, low, cx, y1, fill="#16233a")

    def _cell(self, cell_id, x, y, w, h, big=False):
        cell = self.state.cells[cell_id]
        color = to_hex_color(*cell.color) if cell.text else "#1e2c40"
        text = cell.text or f"·{cell_id:X}"
        text = "".join(ICON_GLYPHS.get(ord(ch), ch) for ch in text)

        size = max(7, int(11 * self.scale * (1.25 if big else 1.0)))
        # Consolas is monospaced at roughly 0.55 em; clip rather than let a
        # long string bleed across neighbouring cells, which is what the
        # hardware does with its own fixed cell widths.
        budget = max(1, int((w - 8) / (size * 0.62)))
        if len(text) > budget:
            text = text[:budget]

        anchor, tx = "center", x + w / 2
        if cell.align == ALIGN_LEFT:
            anchor, tx = "w", x + 4
        elif cell.align == ALIGN_RIGHT:
            anchor, tx = "e", x + w - 4
        self.canvas.create_text(tx, y + h / 2, text=text, fill=color,
                                anchor=anchor, font=("Consolas", size))

    def draw_strip(self):
        for index, box in enumerate(layout.STRIP_LEDS):
            x0, y0, x1, y1 = self.px(box)
            lit = self.state.strip[index] >= 64
            self.canvas.create_oval(x0, y0, x1, y1,
                                    fill="#ff4a3a" if lit else "#2a1512",
                                    outline="")

    def draw_buttons(self):
        for name, box in layout.BUTTONS.items():
            cc = BUTTONS[name]
            x0, y0, x1, y1 = self.px(box)
            level = self.state.buttons.get(cc, 0)
            rgb = self.state.button_colors.get(cc)
            if rgb and any(rgb):
                self.canvas.create_rectangle(x0, y0, x1, y1,
                                             fill=to_hex_color(*rgb),
                                             outline="#000000")
            elif level >= 64:
                self.canvas.create_rectangle(x0, y0, x1, y1, fill="#f0f0f4",
                                             outline="#000000")
            elif level > 0:
                self.canvas.create_rectangle(x0, y0, x1, y1, fill="#5a5a64",
                                             outline="#000000", stipple="gray50")
            if self.show_labels:
                self.canvas.create_text((x0 + x1) / 2, y0 - 6, text=name,
                                        fill="#9a9aa4", font=("Consolas", 7))
            self._register(
                (x0, y0, x1, y1),
                on_press=lambda c=cc, n=name: self._send_cc(c, 127, n),
                on_release=lambda c=cc, n=name: self._send_cc(c, 0, n))

    def draw_knobs(self):
        for index, spec in enumerate(layout.KNOBS):
            box = self.circle(spec)
            self._register(box, encoder=f"knob{index + 1}")
            if self.show_calibration:
                self.canvas.create_oval(*box, outline="#39d0ff")
        box = self.circle(layout.WHEEL)
        self._register(box, encoder="wheel")
        if self.show_calibration:
            self.canvas.create_oval(*box, outline="#39d0ff")

    def draw_calibration(self):
        """Outline every hit region so misregistration is obvious."""
        for box in layout.PADS:
            self.canvas.create_rectangle(*self.px(box), outline="#39ff88")
        for box in layout.BUTTONS.values():
            self.canvas.create_rectangle(*self.px(box), outline="#ffbb33")
        for box in layout.STRIP_LEDS:
            self.canvas.create_rectangle(*self.px(box), outline="#ff5a3c")
        self.canvas.create_rectangle(*self.px(layout.SCREEN), outline="#39d0ff")
        self.canvas.create_rectangle(*self.px(layout.STRIP_BODY),
                                     outline="#8866ff")

    def draw_status(self):
        native = "NATIVE MODE" if self.state.native else "standalone"
        self.canvas.create_text(
            12, self.height - 14, text=native, anchor="w",
            fill="#5ce07a" if self.state.native else DIM,
            font=("Consolas", 10, "bold"))
        self.canvas.create_text(
            160, self.height - 14,
            text=f"unexplained: {len(self.state.unknown)}", anchor="w",
            fill="#e0a05c" if self.state.unknown else DIM,
            font=("Consolas", 9))
        self.canvas.create_text(
            self.canvas.winfo_reqwidth() - 12, self.height - 14, anchor="e",
            text="c calibration   g photo   l labels   q quit",
            fill="#4a4a52", font=("Consolas", 8))

    # -- outbound ---------------------------------------------------------

    def _send_note(self, note, velocity):
        self.server.send_input([NOTE_ON, note, velocity])
        self.state.note(f"-> note {note:02X} vel {velocity}")

    def _send_cc(self, cc, value, name):
        self.server.send_input([CC, cc, value])
        self.state.note(f"-> {name} CC {cc:02X} = {value}")

    def sync_log(self):
        wanted = "\n".join(self.state.log[-7:])
        if self.logbox.get("1.0", tk.END).strip() != wanted.strip():
            self.logbox.delete("1.0", tk.END)
            self.logbox.insert("1.0", wanted)


def main():
    parser = argparse.ArgumentParser(description="ATOM SQ GUI simulator")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--width", type=int, default=1500,
                        help="canvas width; panel geometry scales with it")
    parser.add_argument("--calibrate", action="store_true",
                        help="start with the alignment outlines visible")
    args = parser.parse_args()

    state = PanelState()
    server = Server(Decoder(state), args.port)
    server.start()
    state.note(f"listening on udp 127.0.0.1:{args.port}")

    root = tk.Tk()
    ui = SimulatorUI(root, state, server, args.width)
    ui.show_calibration = args.calibrate
    root.mainloop()


if __name__ == "__main__":
    main()
