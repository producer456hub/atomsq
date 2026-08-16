#!/usr/bin/env python3
"""Probe the undocumented 0x13 / 0x14 SysEx commands.

These appear in the community Bitwig extension and in none of PreSonus's own
code. Its author claims 0x13 controls the button lights / display ownership and
0x14 controls whether the navigation keys emit MIDI or are captured by the
host.

The nav-key claim is objectively testable: set the flag, then watch whether
pressing a nav key still produces MIDI. That is what this does, so the answer
does not depend on anyone squinting at a panel.

    python modes.py replies     send each command, log anything sent back
    python modes.py navkeys     interactive A/B test of the 0x14 claim

Safety: every run ends by restoring 0x13/0x14 to 0 and leaving native mode, so
nothing persists. The command space is NOT blind-scanned — this device exposes
a USB DFU interface, so an unknown command id could plausibly detach it into
the bootloader. Only the two documented-by-community ids are touched.
"""

import sys
import time

from atomsq import (ATOMSQ_ID, PRESONUS_ID, SYSEX_END, SYSEX_START, AtomSQ,
                    BUTTONS, describe, target_from_argv)
from listen import name_for

NAV_KEYS = {BUTTONS[name]: name
            for name in ("up", "down", "left", "right",
                         "wheel_left", "wheel_right")}


def command(cmd: int, arg: int):
    return [SYSEX_START] + PRESONUS_ID + [ATOMSQ_ID, cmd, arg, SYSEX_END]


def drain(device, seconds: float):
    """Collect everything the device sends during `seconds`."""
    got = []
    deadline = time.time() + seconds
    while time.time() < deadline:
        for _delta, message in device.poll():
            got.append(message)
        time.sleep(0.005)
    return got


def mode_replies(device):
    """Send each command/argument and log any response."""
    print("watching for replies to 0x13 / 0x14\n")
    for cmd in (0x13, 0x14):
        for arg in (0x00, 0x01):
            message = command(cmd, arg)
            drain(device, 0.15)          # clear the queue first
            device.send(message)
            print("-> " + " ".join(f"{b:02X}" for b in message))
            replies = drain(device, 0.4)
            if replies:
                for reply in replies:
                    print(f"   <- {describe(reply)}")
            else:
                print("   <- (silent)")
    print("\nA silent device means these are write-only state flags, which is "
          "what a mode switch should look like.")


def wait_for_nav(device, timeout: float = 40.0):
    """Block until a nav key is pressed, so the phase is self-paced.

    Without this the timer starts the instant the script does, and whether the
    test works depends on how fast someone can get to the device — which is a
    property of the harness, not of the device.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        for _delta, message in device.poll():
            if len(message) >= 3 and (message[0] & 0xF0) == 0xB0 \
                    and message[1] in NAV_KEYS:
                return True
        time.sleep(0.005)
    return False


def count_nav(device, seconds: float, label: str, wait: bool = True):
    print(f"\n{label}")
    print("  press any nav key to start this phase "
          "(up/down/left/right or the wheel arrows)...")
    if wait:
        if wait_for_nav(device):
            print("  got one - keep pressing")
        else:
            print("  nothing seen in 40s")
            return 0
    print(f"  counting for {seconds:g}s...")
    messages = drain(device, seconds)
    nav_hits = 0
    other = 0
    for message in messages:
        if len(message) >= 3 and (message[0] & 0xF0) == 0xB0 \
                and message[1] in NAV_KEYS:
            nav_hits += 1
            print(f"    {name_for(message)}")
        elif message and message[0] != 0xF0:
            other += 1
    print(f"  -> {nav_hits} nav-key messages, {other} other messages")
    return nav_hits


def mode_navkeys(device):
    """A/B the 0x14 claim: does setting it silence the nav keys?"""
    print("Testing the claim that 0x14 controls nav-key capture.")
    print("Press the SAME keys the same number of times in both phases.")

    device.send(command(0x13, 0x01))
    device.send(command(0x14, 0x00))
    time.sleep(0.2)
    with_midi = count_nav(device, 12.0, "PHASE A — 0x14 = 00")

    device.send(command(0x14, 0x01))
    time.sleep(0.2)
    # Phase B must NOT wait for a press: if the flag works, no press will ever
    # arrive and waiting would hang until the timeout, then report zero for the
    # wrong reason. Just count for the same window.
    print("\nPHASE B — 0x14 = 01")
    print("  press the same keys the same number of times, now.")
    without = count_nav(device, 12.0, "counting", wait=False)

    print("\n--- result ---")
    if with_midi and not without:
        print("CONFIRMED: 0x14=01 stops the nav keys emitting MIDI.")
    elif with_midi and without:
        print(f"NOT confirmed: keys still emitted MIDI in both phases "
              f"({with_midi} vs {without}). Either the flag does something "
              f"else, or it needs 0x13 set differently.")
    elif not with_midi and not without:
        print("INCONCLUSIVE: no nav-key MIDI in either phase — were the keys "
              "actually pressed? Check the raw stream with listen.py.")
    else:
        print(f"BACKWARDS from the claim: {with_midi} in phase A, "
              f"{without} in phase B.")


def main():
    target = target_from_argv()
    mode = sys.argv[1] if len(sys.argv) > 1 else "replies"

    with AtomSQ(target=target) as device:
        try:
            if mode == "replies":
                mode_replies(device)
            elif mode == "navkeys":
                mode_navkeys(device)
            else:
                print(__doc__)
                return 1
        finally:
            # Restore both flags whatever happened.
            device.send(command(0x14, 0x00))
            device.send(command(0x13, 0x00))
            print("\n[0x13 and 0x14 restored to 00]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
