#!/usr/bin/env python3
"""Do the buttons send a RELEASE, or only a press?

    python hold.py                 walk the buttons the design depends on
    python hold.py --all           walk every button in BUTTONS
    python hold.py --standalone    test without claiming native mode

This is not a curiosity. A host that wants "hold X, press Y" combinations needs
the *release* edge to know when the modifier is let go. If these buttons are
press-only, every hold-combination has to be built some other way — as a toggle,
or on a timer — and that is a design decision, not an implementation detail.

`surface.xml` declares the buttons as transmitting CC and says nothing about
what a release looks like, so this asks the hardware.

THE DEVICE TELLS YOU WHAT TO PRESS. The button it wants is LIT, its name is on
the main line, and for the six soft keys the word PRESS appears in that key's own
screen cell. Hold it, let go, and it moves on by itself.

⚠️ SELF-PACED, deliberately, and it says so because two earlier versions got this
wrong in opposite directions. The first walked a fixed list on 6-second timers
and marched through every button before a hand could reach the unit — six
SKIPPEDs and no conclusion. The second waited properly but stopped telling you
which button it wanted, so the panel just said "press anything". This one waits
indefinitely for the specific button it has lit.
"""

import sys
import time

from atomsq import BUTTONS, CC, AtomSQ, target_from_argv

NAME_FOR_CC = {cc: name for name, cc in BUTTONS.items()}

# The buttons the ATOM SQ control design actually leans on, most load-bearing
# first. `up` is deliberately last: the arrows are the one family the repo flags
# as special (command 0x14 claims to govern whether nav keys emit MIDI at all),
# so they are the least representative evidence for the rest of the panel.
CRITICAL = ["shift", "A", "lcd1", "song", "play", "up"]

# Soft keys own two screen cells each: line 1 and line 2.
SOFT_CELLS = {"lcd1": (0x00, 0x03), "lcd2": (0x01, 0x04), "lcd3": (0x02, 0x05),
              "lcd4": (0x08, 0x0B), "lcd5": (0x09, 0x0C), "lcd6": (0x0A, 0x0D)}

WHITE = (0x7F, 0x7F, 0x7F)
GREEN = (0x00, 0x7F, 0x20)
RED = (0x7F, 0x00, 0x00)
AMBER = (0x7F, 0x50, 0x00)
DARK = (0x00, 0x00, 0x00)

MAIN1, MAIN2 = 0x06, 0x07


def banner(dev, line1, line2, rgb=WHITE):
    dev.screen(MAIN1, str(line1)[:50], rgb)
    dev.screen(MAIN2, str(line2)[:50], rgb)


def point_at(dev, name, index, total):
    """Light the wanted button and name it, so the unit is self-explanatory."""
    dev.buttons_off()
    for cells in SOFT_CELLS.values():
        dev.screen(cells[0], "", DARK)
        dev.screen(cells[1], "", DARK)
    dev.button_led(BUTTONS[name], 127)
    if name in SOFT_CELLS:
        line1, line2 = SOFT_CELLS[name]
        dev.screen(line1, "PRESS", AMBER)
        dev.screen(line2, "+HOLD", AMBER)
    banner(dev, f"HOLD  {name.upper()}", f"{index}/{total}  then let go", AMBER)


def wait_for(dev, cc, seen, stop_after=None):
    """Wait for a message on `cc`. Records every button seen along the way.

    Returns the value of the first message on `cc`, or None if `stop_after`
    seconds elapse (used only for the release window; the press wait is
    unbounded, because the human is the clock).
    """
    deadline = None if stop_after is None else time.time() + stop_after
    while deadline is None or time.time() < deadline:
        for _delta, message in dev.poll():
            if not message or len(message) < 3 or message[0] & 0xF0 != CC:
                continue
            addr, value = message[1], message[2]
            name = NAME_FOR_CC.get(addr)
            if name is None:
                continue                     # an encoder, or pad pressure
            seen.setdefault(name, []).append(value)
            if addr == cc:
                return value
        time.sleep(0.002)
    return None


def main():
    target = target_from_argv()
    native = "--standalone" not in sys.argv
    names = list(BUTTONS) if "--all" in sys.argv else CRITICAL

    print("Do the buttons send a RELEASE, or only a press?")
    print(f"target={target}  native={native}  buttons={len(names)}")
    print("\nThe device lights the button it wants. Hold it, then let go.\n")

    seen: dict[str, list[int]] = {}
    verdicts: dict[str, bool] = {}

    with AtomSQ(native=native, target=target) as dev:
        dev.screen_clear()
        dev.buttons_off()
        banner(dev, "HOLD TEST", "the lit button is the one to press", WHITE)
        time.sleep(1.5)

        for i, name in enumerate(names, 1):
            cc = BUTTONS[name]
            point_at(dev, name, i, len(names))
            print(f"  {name:14} CC 0x{cc:02X}  — waiting…", flush=True)

            press = wait_for(dev, cc, seen)                  # unbounded
            banner(dev, f"{name.upper()} = {press}", "now LET GO", WHITE)
            release = wait_for(dev, cc, seen, stop_after=5.0)

            got = release == 0
            verdicts[name] = got
            print(f"      press {press} · release "
                  f"{release if release is not None else '(none within 5s)'}"
                  f"  ->  {'PRESS + RELEASE' if got else 'PRESS ONLY'}")
            banner(dev, f"{name.upper()}  {'PRESS+RELEASE' if got else 'PRESS ONLY'}",
                   f"{i}/{len(names)} done", GREEN if got else RED)
            time.sleep(0.9)

        dev.buttons_off()
        print("\n" + "=" * 58)
        for name in names:
            vals = seen.get(name, [])
            print(f"  {name:14} {str(vals):26} "
                  f"{'PRESS + RELEASE' if verdicts.get(name) else 'PRESS ONLY'}")

        good = [n for n in names if verdicts.get(n)]
        bad = [n for n in names if not verdicts.get(n)]
        print()
        if not bad:
            print(f"ALL {len(good)} send a RELEASE (value 0).")
            print("Hold-combinations are safe to build on the release edge.")
            banner(dev, f"ALL {len(good)} SEND RELEASE", "holds are safe", GREEN)
        elif not good:
            print("NONE sent a release. Hold-combinations cannot use the release edge.")
            banner(dev, "PRESS ONLY", "holds need another mechanism", RED)
        else:
            print(f"MIXED — release: {', '.join(good)}")
            print(f"        press only: {', '.join(bad)}")
            print("Any hold design must be restricted to the first group.")
            banner(dev, "MIXED", ", ".join(bad) + " = press only", AMBER)

        extra = {n: v for n, v in seen.items() if n not in names}
        if extra:
            print(f"\nalso seen: " + ", ".join(f"{n}={v}" for n, v in extra.items()))
        time.sleep(2.0)


if __name__ == "__main__":
    main()
