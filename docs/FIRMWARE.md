# ATOM SQ — Firmware and DFU

Unit: serial `ATSC20100175`, firmware **1.17** (`bcdDevice 0x0117`, identity reply bytes
`01 17` read as BCD).

Tags as in `PROTOCOL.md`: **[V]** verified here, **[C]** community, **[?]** inferred.

---

## The DFU interface

**[V]** Interface 2 is `0xFE / 0x01 / 0x01` — USB DFU, runtime. Read on Linux with
`lsusb -v -d 194f:020a`; no driver binding and no `dfu-util` needed for this part.

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

`dfu-util 0.11` sees it unprivileged once the udev rule in `tools/` is installed:

```
Found Runtime: [194f:020a] ver=0117, devnum=2, cfg=1, intf=2, path="3-1", alt=0,
               name="UNKNOWN", serial="ATSC20100175"
```

## A bare DFU_DETACH is refused

**[V]** Attempted with `dfu-util -d 194f:020a -e` (upload-only workflow — no `-D` anywhere):

```
Setting Alternate Interface zero...
Determining device status...
DFU state(10) = dfuERROR, status(14) = errUNKNOWN
dfuERROR, clearing status
dfu-util: error clear_status
```

The runtime interface reports itself already in **`dfuERROR`** and then refuses `DFU_CLRSTATUS`.
The device never re-enumerated in DFU mode.

**Nothing was written, and the device was unaffected**: both MIDI ports came back, and the
identity request still answered normally with firmware 1.17.

Read: the DFU descriptor is advertised, but the standard DFU entry path is inert until the device
is put into update mode by other means. The interface is effectively a stub in normal operation.

## How PreSonus actually enters update mode

**[C]** From PreSonus's own knowledge base (ATOM SQ: Firmware Reset): disconnect the unit, then
**hold the Setup button while reconnecting USB**. No pads light, the Sync/Studio One light turns
red, and the screen reads `Updating Firmware 0%`. Universal Control then offers an Update
Firmware button.

That is a bootloader/recovery mode entered by a physical button combination at power-on — which
is exactly why a software `DFU_DETACH` gets nowhere. **[?]** In that state the DFU interface is
very likely live, and `dfu-util -U` would be able to upload the image.

## Why that has not been attempted

Entering recovery mode is a documented, vendor-sanctioned procedure and leaving it is a replug.
The unquantified risk is what the bootloader does to the application region *on entry*. The screen
reading `Updating Firmware 0%` suggests it waits for a download rather than pre-erasing, and the
normal case is that the application stays intact until a download actually starts — but that is an
assumption, not something we have verified.

**If it does pre-erase, a valid firmware image becomes mandatory to get the unit working again,
and we do not have one.** So the safe order is:

1. Obtain the official firmware image first, from Universal Control.
2. Only then enter recovery mode and try `dfu-util -U`, with a known-good image in hand as the
   recovery path.

Doing it the other way round risks needing the thing we went in to get.

## Getting the official image

**[V]** Universal Control is not anonymously downloadable — `pae-web.presonusmusic.com` returns
403 and the legacy product page now redirects to the site root. It requires a My.PreSonus account
sign-in, so the installer has to be fetched by hand.

Once we have the installer, extraction is offline work with no hardware risk: find the ATOM SQ
payload, identify the container, entropy-scan for encryption, and look for an ARM vector table to
pin the MCU and load address.

If that image turns out to be encrypted, dumping from the device becomes the only route to
readable firmware — and at that point the recovery-mode upload is worth the risk, because the
encrypted vendor image still serves as the restore path.

## Open

1. Is the application region intact while in recovery mode? **[?]**
2. Does the DFU interface leave `dfuERROR` once in recovery mode? **[?]**
3. Is the Universal Control payload encrypted? **[?]**
4. What the second MIDI port (`ATM SQ Control`) carries — a plausible candidate for the
   configuration and update channel Universal Control uses. **[?]**
