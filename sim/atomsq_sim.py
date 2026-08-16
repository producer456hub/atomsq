#!/usr/bin/env python3
"""ATOM SQ GUI simulator.

A software ATOM SQ that speaks the real protocol. Two jobs:

1. **Visualiser** - decode the exact bytes we send and show what the hardware
   would do. Every LED and screen cell here is driven by the same message
   parsing the device does, so if the sim looks wrong our bytes are wrong.
2. **Stand-in** - develop and test with no hardware attached, and generate
   input (clicks on pads/buttons/knobs) back to the driving script.

Transport is a UDP socket carrying raw MIDI messages, one message per datagram.
That keeps it dead simple and lets any language drive it.

    python sim/atomsq_sim.py                 # listen on 127.0.0.1:9001
    python sim/atomsq_sim.py --port 9100

Then point a probe at it:

    python probe/screen.py map --target sim

Tkinter only - no third-party GUI dependency.
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

from atomsq import (  # noqa: E402
    ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT, BUTTONS, CC, CELL_COUNT, CELLS,
    CMD_SCREEN_WRITE, ENCODERS, ICONS, NOTE_OFF, NOTE_ON, PAD_COUNT,
    PAD_NOTE_START, PAD_LED_BLINK, PAD_LED_OFF, PAD_LED_ON, PAD_LED_PULSE,
    PRESONUS_ID, ATOMSQ_ID, STRIP_LED_COUNT, STRIP_LED_START, SYSEX_START,
)

DEFAULT_PORT = 9001

# --- palette -------------------------------------------------------------

BG = "#141416"
PANEL = "#1e1e21"
EDGE = "#2c2c31"
INK = "#d8d8dc"
DIM = "#6a6a72"
SCREEN_BG = "#04060a"

PAD_ROWS, PAD_COLS = 2, 16

# Reverse lookups so decoded addresses can be named in the GUI.
CC_TO_BUTTON = {cc: name for name, cc in BUTTONS.items()}
CC_TO_ENCODER = {cc: name for name, cc in ENCODERS.items()}
CELL_BY_ID = {cell: name for name, cell in CELLS.items()}
ICON_CHARS = {code: name for name, code in ICONS.items()}


def to_hex_color(r: int, g: int, b: int) -> str:
    """7-bit device RGB -> 8-bit screen hex."""
    return "#%02x%02x%02x" % (min(255, r * 2), min(255, g * 2), min(255, b * 2))


class Cell:
    __slots__ = ("text", "color", "align")

    def __init__(self):
        self.text = ""
        self.color = (0x7F, 0x7F, 0x7F)
        self.align = ALIGN_CENTER


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
        self.unknown = []          # messages the decoder could not explain

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
        status, rest = message[0], message[1:]
        kind, channel = status & 0xF0, status & 0x0F
        if len(rest) < 2:
            return
        addr, value = rest[0], rest[1]

        # Native mode: Note Off on channel 16, note 0.
        if kind == NOTE_OFF and channel == 15 and addr == 0x00:
            self.state.native = value >= 0x40
            self.state.note(
                f"native mode {'ON' if self.state.native else 'OFF'}")
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
            return
        pad = self.state.pads[index]
        if channel == 0:
            pad.state = value
        elif channel in (1, 2, 3):
            # Status channel selects the colour component.
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
        command = body[4]
        args = body[5:]
        if command == CMD_SCREEN_WRITE:
            if len(args) < 5:
                return
            cell_id, r, g, b, align = args[:5]
            text = "".join(chr(c) for c in args[5:])
            if 0 <= cell_id < CELL_COUNT:
                cell = self.state.cells[cell_id]
                cell.text, cell.color, cell.align = text, (r, g, b), align
        else:
            # 0x13 / 0x14 land here - exactly what we want to see logged.
            self.state.note(
                f"sysex cmd 0x{command:02X} args="
                + " ".join(f"{a:02X}" for a in args))
            self.state.unknown.append(message)


class Server(threading.Thread):
    """UDP listener: inbound datagram = one raw MIDI message."""

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
        """Send a control event back to whoever is driving the sim."""
        if self.client:
            try:
                self.sock.sendto(bytes(message), self.client)
            except OSError:
                pass


class PhotoOverlay:
    """A top-down photo of the real unit, blended over the vector panel.

    This is the compliance check: line the photo up with the drawn panel and
    any control that is the wrong size, in the wrong place, or missing shows up
    immediately. Calibration (offset/scale/alpha) persists to overlay.json so
    it survives a restart.
    """

    CONFIG = Path(__file__).resolve().parent / "overlay.json"

    def __init__(self, path: str | None):
        self.available = False
        self.enabled = False
        self.image = None
        self.photo = None
        self.alpha = 0.45
        self.x = 0
        self.y = 0
        self.scale = 1.0
        self._cache_key = None
        if not path:
            return
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            print("photo overlay needs Pillow: pip install pillow")
            return
        source = Path(path)
        if not source.exists():
            print(f"photo not found: {source}")
            return
        from PIL import Image
        self.image = Image.open(source).convert("RGBA")
        self.available = True
        self.enabled = True
        self.load()
        print(f"overlay loaded: {source.name} {self.image.size}")

    def load(self) -> None:
        if not self.CONFIG.exists():
            return
        import json
        try:
            data = json.loads(self.CONFIG.read_text())
        except (OSError, ValueError):
            return
        self.x = data.get("x", self.x)
        self.y = data.get("y", self.y)
        self.scale = data.get("scale", self.scale)
        self.alpha = data.get("alpha", self.alpha)

    def save(self) -> None:
        import json
        self.CONFIG.write_text(json.dumps(
            {"x": self.x, "y": self.y, "scale": self.scale,
             "alpha": self.alpha}, indent=2))

    def rendered(self):
        """Return a PhotoImage at the current scale and alpha, cached."""
        if not self.available or not self.enabled:
            return None
        key = (round(self.scale, 3), round(self.alpha, 3))
        if key != self._cache_key:
            from PIL import Image, ImageTk
            width = max(1, int(self.image.width * self.scale))
            height = max(1, int(self.image.height * self.scale))
            scaled = self.image.resize((width, height), Image.LANCZOS)
            alpha_band = scaled.getchannel("A").point(
                lambda a: int(a * self.alpha))
            scaled.putalpha(alpha_band)
            self.photo = ImageTk.PhotoImage(scaled)
            self._cache_key = key
        return self.photo

    def status(self) -> str:
        if not self.available:
            return ""
        onoff = "on" if self.enabled else "off"
        return (f"overlay {onoff}  x={self.x} y={self.y} "
                f"scale={self.scale:.2f} alpha={self.alpha:.2f}   "
                "[o]toggle [arrows]move [+/-]scale [,/.]alpha [s]save")


class SimulatorUI:
    def __init__(self, root: tk.Tk, state: PanelState, server: Server,
                 overlay: "PhotoOverlay | None" = None):
        self.root = root
        self.state = state
        self.server = server
        self.overlay = overlay or PhotoOverlay(None)
        self.blink_phase = 0.0

        root.title(f"ATOM SQ simulator — udp 127.0.0.1:{server.port}")
        root.configure(bg=BG)

        self.canvas = tk.Canvas(root, width=1180, height=560, bg=BG,
                                highlightthickness=0)
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.logbox = tk.Text(root, height=9, bg="#0c0c0e", fg=DIM,
                              insertbackground=INK, font=("Consolas", 9),
                              highlightthickness=0, borderwidth=0)
        self.logbox.pack(side=tk.BOTTOM, fill=tk.X)

        self.hit_targets = []  # (x0, y0, x1, y1, callback)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self._pressed = None
        self._hover_encoder = None
        self.canvas.bind("<Motion>", self._on_motion)

        root.bind("<Key>", self._on_key)
        self.tick()

    # -- overlay controls -------------------------------------------------

    def _on_key(self, event):
        overlay = self.overlay
        if not overlay.available:
            return
        step = 10 if (event.state & 0x0001) else 1  # shift = coarse
        key = event.keysym.lower()
        if key == "o":
            overlay.enabled = not overlay.enabled
        elif key == "left":
            overlay.x -= step
        elif key == "right":
            overlay.x += step
        elif key == "up":
            overlay.y -= step
        elif key == "down":
            overlay.y += step
        elif key in ("plus", "equal"):
            overlay.scale = min(4.0, overlay.scale * 1.02)
        elif key == "minus":
            overlay.scale = max(0.05, overlay.scale / 1.02)
        elif key == "comma":
            overlay.alpha = max(0.0, overlay.alpha - 0.05)
        elif key == "period":
            overlay.alpha = min(1.0, overlay.alpha + 0.05)
        elif key == "s":
            overlay.save()
            self.state.note(f"overlay calibration saved to {overlay.CONFIG.name}")

    # -- geometry ---------------------------------------------------------

    def _register(self, box, on_press=None, on_release=None, encoder=None):
        self.hit_targets.append((box, on_press, on_release, encoder))

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
        delta = 1 if event.delta > 0 else 0x41
        self.server.send_input([CC, cc, delta])
        self.state.note(f"-> {self._hover_encoder} delta "
                        f"{'+1' if event.delta > 0 else '-1'} (CC {cc:02X}={delta:02X})")

    # -- drawing ----------------------------------------------------------

    def tick(self):
        self.blink_phase = (self.blink_phase + 0.08) % 1.0
        self.canvas.delete("all")
        self.hit_targets.clear()
        self.draw_screen(20, 16, 560, 210)
        self.draw_knobs(600, 16)
        self.draw_strip(600, 168)
        self.draw_pads(20, 250)
        self.draw_buttons(600, 250)
        self.draw_status(20, 520)
        self.draw_overlay()
        self.sync_log()
        self.root.after(50, self.tick)

    def draw_overlay(self):
        """Drawn last so it sits on top of the vector panel for comparison."""
        photo = self.overlay.rendered()
        if photo is not None:
            self.canvas.create_image(self.overlay.x, self.overlay.y,
                                     image=photo, anchor="nw")
        status = self.overlay.status()
        if status:
            self.canvas.create_text(20, 542, text=status, fill="#7a7a84",
                                    anchor="w", font=("Consolas", 8))

    def draw_screen(self, x, y, w, h):
        self.canvas.create_rectangle(x - 6, y - 6, x + w + 6, y + h + 6,
                                     fill=PANEL, outline=EDGE)
        self.canvas.create_rectangle(x, y, x + w, y + h, fill=SCREEN_BG,
                                     outline="#0d1522")

        col_w = w / 3
        # Top band: soft buttons 1-3 (cells 0-2 line 1, 3-5 line 2).
        # Middle band: the two wide main lines (cells 6, 7).
        # Bottom band: soft buttons 4-6 (cells 8-10 line 1, 11-13 line 2).
        top_ids = [(0, 3), (1, 4), (2, 5)]
        bottom_ids = [(8, 11), (9, 12), (10, 13)]
        band = h * 0.32
        mid_y = y + band

        for col, (l1, l2) in enumerate(top_ids):
            cx = x + col * col_w
            self._cell_text(l1, cx, y + 6, col_w, 20)
            self._cell_text(l2, cx, y + 28, col_w, 20)
            if col:
                self.canvas.create_line(cx, y, cx, mid_y, fill="#16233a")

        self.canvas.create_rectangle(x, mid_y, x + w, mid_y + band,
                                     fill="#070d18", outline="#16233a")
        self._cell_text(6, x, mid_y + 8, w, 22, big=True)
        self._cell_text(7, x, mid_y + 34, w, 22, big=True)

        bottom_y = mid_y + band
        for col, (l1, l2) in enumerate(bottom_ids):
            cx = x + col * col_w
            self._cell_text(l1, cx, bottom_y + 8, col_w, 20)
            self._cell_text(l2, cx, bottom_y + 30, col_w, 20)
            if col:
                self.canvas.create_line(cx, bottom_y, cx, y + h, fill="#16233a")

        # The six soft buttons flanking the screen, top row then bottom row.
        for col in range(3):
            for row, base in ((0, 0), (1, 3)):
                name = f"lcd{col + base + 1}"
                cc = BUTTONS[name]
                bx = x + col * col_w + col_w / 2 - 26
                by = y - 4 if row == 0 else y + h - 16
                self._button(bx, by, 52, 14, name, cc, tiny=True)

    def _cell_text(self, cell_id, x, y, w, h, big=False):
        cell = self.state.cells[cell_id]
        color = to_hex_color(*cell.color) if cell.text else "#243247"
        display = cell.text or f"·{cell_id:X}"
        # Render private-font control codes as a readable placeholder.
        display = "".join(
            f"<{ICON_CHARS[ord(ch)]}>" if ord(ch) in ICON_CHARS else ch
            for ch in display)
        anchor, tx = "center", x + w / 2
        if cell.align == ALIGN_LEFT:
            anchor, tx = "w", x + 6
        elif cell.align == ALIGN_RIGHT:
            anchor, tx = "e", x + w - 6
        self.canvas.create_text(
            tx, y + h / 2, text=display, fill=color, anchor=anchor,
            font=("Consolas", 13 if big else 10, "bold" if big else "normal"))

    def draw_knobs(self, x, y):
        for i in range(8):
            col, row = i % 4, i // 4
            cx = x + 60 + col * 82
            cy = y + 40 + row * 76
            name = f"knob{i + 1}"
            self.canvas.create_oval(cx - 24, cy - 24, cx + 24, cy + 24,
                                    fill="#26262b", outline="#3a3a42", width=2)
            self.canvas.create_text(cx, cy, text=str(i + 1), fill=DIM,
                                    font=("Consolas", 10))
            self.canvas.create_text(cx, cy + 34, text=f"CC {ENCODERS[name]:02X}",
                                    fill="#4a4a52", font=("Consolas", 7))
            self._register((cx - 24, cy - 24, cx + 24, cy + 24), encoder=name)

    def draw_strip(self, x, y):
        self.canvas.create_text(x, y - 10, text="touch strip  CC 37-4F",
                                fill="#4a4a52", anchor="w",
                                font=("Consolas", 7))
        led_w = 13
        for i in range(STRIP_LED_COUNT):
            lit = self.state.strip[i] >= 64
            self.canvas.create_rectangle(
                x + i * led_w, y, x + i * led_w + led_w - 2, y + 18,
                fill="#3ad0ff" if lit else "#1d2126",
                outline="#101216")

    def draw_pads(self, x, y):
        pad_w, pad_h, gap = 62, 62, 6
        for row in range(PAD_ROWS):
            for col in range(PAD_COLS):
                # pad[0][*] is the lower bank (notes 0x24-0x33); draw it below.
                index = row * PAD_COLS + col
                pad = self.state.pads[index]
                note = PAD_NOTE_START + index
                px = x + col * (pad_w + gap)
                # Staggered: the upper bank sits half a pad to the right.
                py = y + (PAD_ROWS - 1 - row) * (pad_h + gap)
                px += 0 if row == 0 else pad_w / 2
                self._pad(px, py, pad_w, pad_h, pad, note, index)

    def _pad(self, x, y, w, h, pad, note, index):
        on = pad.state != PAD_LED_OFF
        color = "#1b1b1f"
        if on:
            r, g, b = pad.color
            if pad.state == PAD_LED_BLINK:
                on = self.blink_phase < 0.5
            elif pad.state == PAD_LED_PULSE:
                scale = 0.35 + 0.65 * abs(0.5 - self.blink_phase) * 2
                r, g, b = int(r * scale), int(g * scale), int(b * scale)
            color = to_hex_color(r, g, b) if on else "#1b1b1f"
        self.canvas.create_rectangle(x, y, x + w, y + h, fill=color,
                                     outline="#34343c")
        self.canvas.create_text(x + w / 2, y + h - 9, text=f"{note:02X}",
                                fill="#5a5a62", font=("Consolas", 7))
        self._register(
            (x, y, x + w, y + h),
            on_press=lambda n=note: self._send_note(n, 100),
            on_release=lambda n=note: self._send_note(n, 0))

    def _send_note(self, note, velocity):
        self.server.send_input([NOTE_ON, note, velocity])
        self.state.note(f"-> pad note {note:02X} vel {velocity}")

    def draw_buttons(self, x, y):
        groups = [
            ("function", ["A", "B", "C", "D", "E", "F", "G", "H"]),
            ("mode", ["song", "inst", "editor", "user", "shift"]),
            ("nav", ["up", "down", "left", "right",
                     "wheel_left", "wheel_right"]),
            ("transport", ["stop", "play", "record", "metronome"]),
        ]
        cy = y
        for title, names in groups:
            self.canvas.create_text(x, cy, text=title, fill="#4a4a52",
                                    anchor="w", font=("Consolas", 7))
            cy += 12
            for i, name in enumerate(names):
                bx = x + (i % 6) * 88
                by = cy + (i // 6) * 30
                self._button(bx, by, 82, 24, name, BUTTONS[name])
            cy += 30 * ((len(names) + 5) // 6) + 12

    def _button(self, x, y, w, h, name, cc, tiny=False):
        level = self.state.buttons.get(cc, 0)
        rgb = self.state.button_colors.get(cc)
        if rgb and any(rgb):
            fill = to_hex_color(*rgb)
        elif level >= 64:
            fill = "#8a8a94"
        elif level > 0:
            fill = "#3c3c44"
        else:
            fill = "#202027"
        self.canvas.create_rectangle(x, y, x + w, y + h, fill=fill,
                                     outline="#3a3a42")
        self.canvas.create_text(
            x + w / 2, y + h / 2, text=name, font=("Consolas", 7),
            fill=INK if level < 64 and not (rgb and any(rgb)) else "#101014")
        self._register(
            (x, y, x + w, y + h),
            on_press=lambda c=cc, n=name: self._send_cc(c, 127, n),
            on_release=lambda c=cc, n=name: self._send_cc(c, 0, n))

    def _send_cc(self, cc, value, name):
        self.server.send_input([CC, cc, value])
        self.state.note(f"-> {name} CC {cc:02X} = {value}")

    def draw_status(self, x, y):
        native = "NATIVE MODE" if self.state.native else "standalone"
        color = "#5ce07a" if self.state.native else DIM
        self.canvas.create_text(x, y, text=native, fill=color, anchor="w",
                                font=("Consolas", 10, "bold"))
        self.canvas.create_text(
            x + 160, y,
            text=f"unexplained messages: {len(self.state.unknown)}",
            fill="#e0a05c" if self.state.unknown else DIM, anchor="w",
            font=("Consolas", 9))

    def sync_log(self):
        wanted = "\n".join(self.state.log[-9:])
        if self.logbox.get("1.0", tk.END).strip() != wanted.strip():
            self.logbox.delete("1.0", tk.END)
            self.logbox.insert("1.0", wanted)


def main():
    parser = argparse.ArgumentParser(description="ATOM SQ GUI simulator")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--photo", metavar="PATH",
                        help="top-down photo of the real unit, blended over "
                             "the panel to check layout compliance")
    args = parser.parse_args()

    state = PanelState()
    server = Server(Decoder(state), args.port)
    server.start()
    state.note(f"listening on udp 127.0.0.1:{args.port}")

    root = tk.Tk()
    SimulatorUI(root, state, server, PhotoOverlay(args.photo))
    root.mainloop()


if __name__ == "__main__":
    main()
