#!/usr/bin/env bash
# Dump the ATOM SQ's firmware over USB DFU. READ ONLY.
#
# The device's DFU functional descriptor advertises "Upload Supported", so it
# will hand its own image back to the host. This script only ever uses
# dfu-util -U (upload, device -> host). It never uses -D (download), so it
# cannot write to the device.
#
# Sequence:
#   1. record the pre-detach state, so we can prove nothing changed
#   2. DFU_DETACH  -> the device re-enumerates in DFU mode
#   3. upload the image
#   4. return it to normal operation
#
# Recovery if anything goes sideways: unplug the USB cable and plug it back in.
# The device boots its application firmware unless a download was performed,
# and this script performs none.
#
#   sudo bash tools/dfu_dump.sh
set -uo pipefail

VID_PID="194f:020a"
OUT_DIR="${OUT_DIR:-/home/david/atomsq/captures}"
STAMP="$(date +%Y%m%d-%H%M%S)"
IMAGE="$OUT_DIR/atomsq-firmware-$STAMP.bin"
LOG="$OUT_DIR/dfu-dump-$STAMP.log"

mkdir -p "$OUT_DIR"
exec > >(tee -a "$LOG") 2>&1

say() { printf '\n=== %s ===\n' "$*"; }

if ! command -v dfu-util >/dev/null 2>&1; then
    echo "dfu-util not installed: sudo apt-get install -y dfu-util"
    exit 1
fi

# Root is not required if the udev rule in this directory is installed — it
# grants the desktop user access to the device by ACL, which is what lets this
# run unattended over SSH.
if [ "$(id -u)" -ne 0 ] && ! dfu-util -l 2>&1 | grep -qi "found"; then
    if dfu-util -l 2>&1 | grep -qi "cannot open\|permission\|access"; then
        echo "no permission to claim the USB interface, and not running as root."
        echo "Install the udev rule once:"
        echo "  sudo install -m644 $(dirname "$0")/60-presonus-atomsq.rules /etc/udev/rules.d/"
        echo "  sudo udevadm control --reload && sudo udevadm trigger"
        echo "or re-run this with sudo."
        exit 1
    fi
fi

say "1. state before touching anything"
lsusb -d "$VID_PID" || { echo "ATOM SQ not on the bus"; exit 1; }
lsusb -v -d "$VID_PID" 2>/dev/null | grep -A9 "Device Firmware Upgrade Interface Descriptor"
echo "--- dfu-util view ---"
dfu-util -l 2>&1 | grep -i "found\|serial" || true

say "2. detaching into DFU mode"
echo "(the device advertises Will Detach, so no host-forced reset is needed)"
dfu-util -d "$VID_PID" -e 2>&1 | tail -5 || true

echo "waiting for it to come back in DFU mode..."
DFU_LINE=""
for _ in $(seq 1 15); do
    sleep 1
    DFU_LINE="$(dfu-util -l 2>/dev/null | grep -i '^Found DFU' | head -1)"
    [ -n "$DFU_LINE" ] && break
done

if [ -z "$DFU_LINE" ]; then
    say "device did not present a DFU-mode interface"
    echo "Still enumerated as:"
    lsusb | grep -i "194f" || echo "  (nothing with VID 194f)"
    dfu-util -l 2>&1 | grep -i found || true
    echo
    echo "Nothing was written. Unplug and replug the cable to be certain the"
    echo "device is back in its normal mode."
    exit 2
fi

echo "$DFU_LINE"
DFU_ID="$(echo "$DFU_LINE" | grep -o '[0-9a-f]\{4\}:[0-9a-f]\{4\}' | head -1)"
echo "DFU-mode device: $DFU_ID"

say "3. uploading the image (device -> host, read only)"
# -a 0 selects the first alt setting; some devices expose several regions.
dfu-util -d "$DFU_ID" -a 0 -U "$IMAGE" 2>&1 | tail -20

if [ -s "$IMAGE" ]; then
    say "image captured"
    ls -l "$IMAGE"
    echo "sha256: $(sha256sum "$IMAGE" | cut -d' ' -f1)"
    echo "--- first 64 bytes ---"
    xxd -l 64 "$IMAGE"
else
    say "no image produced"
    echo "The descriptor advertises Upload Supported, but some bootloaders"
    echo "refuse it in practice. Nothing was written either way."
fi

say "4. returning the device to normal operation"
# From DFU mode, -e asks it to leave; many bootloaders instead need a bus
# reset, which replugging guarantees.
dfu-util -d "$DFU_ID" -e 2>&1 | tail -3 || true
sleep 2
if lsusb -d "$VID_PID" >/dev/null 2>&1; then
    echo "device is back as $VID_PID"
    amidi -l 2>/dev/null | grep -i "ATM SQ" || echo "  (MIDI ports not up yet)"
else
    echo "device has NOT returned to application mode."
    echo ">>> Unplug the USB cable and plug it back in. <<<"
    echo "No download was performed, so the application firmware is intact."
fi

say "done"
echo "log:   $LOG"
echo "image: $IMAGE"
