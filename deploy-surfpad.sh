#!/usr/bin/env bash
# Move the atomsq workspace to surfpad and make it runnable there.
#
# surfpad is aarch64 Linux, so the ATOM SQ needs no driver: the control port is
# class-compliant USB-MIDI, and the DFU interface on MI_02 is directly readable
# with dfu-util, which is the thing Windows will not give us without binding a
# WinUSB driver.
#
#   ./deploy-surfpad.sh            copy + check
#   ./deploy-surfpad.sh --deps     also install missing python packages
set -euo pipefail

HOST="${ATOMSQ_HOST:-david@100.100.203.108}"
REMOTE="${ATOMSQ_REMOTE:-/home/david/atomsq}"
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "==> syncing $HERE -> $HOST:$REMOTE"
if command -v rsync >/dev/null 2>&1; then
    # build/ is excluded from the delete sweep: it only exists on the remote,
    # and wiping it forces a full recompile on every sync.
    rsync -az --delete \
        --exclude '__pycache__' --exclude '*.pyc' --exclude 'captures/*.png' \
        --exclude 'build' --exclude '.git' \
        "$HERE/" "$HOST:$REMOTE/"
else
    # Windows OpenSSH ships scp but not rsync.
    ssh "$HOST" "rm -rf '$REMOTE' && mkdir -p '$REMOTE'"
    scp -q -r "$HERE/." "$HOST:$REMOTE/"
fi
echo "    done"

if [ "${1:-}" = "--deps" ]; then
    echo "==> installing python deps"
    # Debian/Ubuntu keep the system python managed, so prefer distro packages
    # and fall back to a --user pip install.
    ssh "$HOST" 'sudo -n apt-get install -y python3-rtmidi python3-pil.imagetk python3-tk dfu-util 2>/dev/null \
        || pip3 install --user --break-system-packages python-rtmidi pillow' || true
fi

echo "==> checking the remote environment"
ssh "$HOST" "cd '$REMOTE' && python3 - <<'PY'
import shutil, subprocess
for module in ('rtmidi', 'PIL', 'tkinter'):
    try:
        __import__(module)
        print(f'  python {module}: OK')
    except ImportError as exc:
        print(f'  python {module}: MISSING ({exc})')
for tool in ('dfu-util', 'lsusb', 'amidi'):
    print(f'  {tool}: {shutil.which(tool) or \"MISSING\"}')
PY"

echo "==> is the ATOM SQ attached?"
ssh "$HOST" "lsusb 2>/dev/null | grep -i '194f' || echo '  no PreSonus device on the USB bus yet'"
ssh "$HOST" "cd '$REMOTE' && python3 -c \"
import rtmidi
i = rtmidi.MidiIn().get_ports()
o = rtmidi.MidiOut().get_ports()
print('  midi in :', i)
print('  midi out:', o)
\" 2>/dev/null || echo '  (rtmidi not available yet)'"
