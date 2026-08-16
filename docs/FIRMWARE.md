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

## What Universal Control revealed

**[V]** Fender Universal Control **v5.1.1 build 113315** (`Fender_Universal_Control_v5_1_1_113315.exe`,
190 MB, NSIS self-extracting) unpacks with `7z x`. It ships **no firmware images at all** — they
are fetched at update time, and no static firmware URL appears in any binary, so the endpoint is
built at runtime. `https://api.presonus.com/v2` and `https://www.presonus.software` are the
plausible hosts; neither exposes an obvious unauthenticated firmware path.

What it does ship is far more useful:

### Bootloader USB IDs — `Drivers/Atom/x64/PreSonusATOMDFU.inf`

```
"PreSonus ATOM DFU"               = USB\VID_194F&PID_0206&MI_02
"PreSonus ATOM DFU Bootloader"    = USB\VID_194F&PID_0207
"PreSonus ATOM SQ DFU"            = USB\VID_194F&PID_020A&MI_02
"PreSonus ATOM SQ DFU Bootloader" = USB\VID_194F&PID_020B
```

**In recovery mode the ATOM SQ enumerates as `194f:020b`, not `194f:020a`.** Both bind to WinUSB
under device interface GUID `{F253955F-DD15-45F6-89B1-89EE6604629B}`. Driver dated 2025-02-12,
v1.12.0.17397.

### The silicon — `hwaccess/atomdevice.dll`

**[V]** Strings identify the whole stack:

- `ClassOrVendorOutRequest(XMOS_DFU_SELECTIMAGE) failed` → the ATOM SQ is an **XMOS xCORE**
  device. XMOS is the standard choice for class-compliant USB audio/MIDI, which also explains why
  the MIDI side is so clean.
- `thesycon::DfuApi`, `TLDFU_LoadFirmwareImageFromFile`, `TLDFU_RebootDevice`,
  `TLDFU_StartUpgrade`, `TUSBAUDIO_GetFirmwareImage` → the host side is **Thesycon's** TLDFU /
  TUSBAUDIO SDK, not a PreSonus implementation.
- Image formats: `DfuImageRawBinary` and `DfuImageTlBinary` — raw binary, plus a Thesycon
  container variant.
- A note in the binary: *"The flag TLDFU_DEVICE_FLAG_USE_XMOS_DFU_EXTENSIONS is no longer
  supported. See TLDFU_RebootDevice() and TLDFU_StartUpgrade()."*

### Why this changes the risk assessment

XMOS DFU is a **dual-image** design — that is precisely what `XMOS_DFU_SELECTIMAGE` selects
between. Flash holds a **factory image** and an **upgrade image**; the factory image is not
erased by an upgrade and is what the bootloader falls back to. That is the mechanism behind
PreSonus's own documented recovery procedure.

So the earlier worry — that entering recovery mode might leave us with no way back if the
application region were pre-erased — is much weaker than assumed. The factory image is a
manufacturer-provided fallback that a DFU *upload* cannot touch in any case.

It also explains the `dfuERROR` on a bare `DFU_DETACH`: XMOS's DFU entry is a vendor request
(`XMOS_DFU_RESETINTODFU`), not the standard detach, so the standard path was never going to work.

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

## The dump was attempted, and it did not work

**[V]** Recovery mode entered as documented — Setup held while connecting USB. The device
enumerated exactly as the INF predicted:

```
Found DFU: [194f:020b] ver=0015, devnum=3, cfg=1, intf=0, alt=0
```

Bootloader version **0.15**. In DFU mode it presents a single interface (protocol `02` = DFU
mode, versus `01` runtime), only alt setting 0, and negotiates a **2048-byte** transfer size —
32× the 64 bytes it advertises at runtime. It reported `dfuIDLE, status 0, no error condition`,
so the `dfuERROR` seen at runtime is genuinely just the stub state.

`dfu-util -d 194f:020b -a 0 -U` then ran cleanly and returned **3 bytes**:

```
00 21 41
```

Not a firmware image. The bootloader advertises `Upload Supported` in its descriptor and then
returns a short block that terminates the transfer immediately — the "advertises upload but
refuses it in practice" case. Vendors commonly stub `DFU_UPLOAD` precisely to stop firmware being
read out.

**No harm done.** `dfu-util -e` reported `can't detach`, but the device rebooted into application
mode by itself: back as `194f:020a`, both MIDI ports up, identity replying
`F0 7E 7F 06 02 00 01 06 22 00 00 00 00 01 17 00 F7` — still firmware 1.17. Entering and leaving
recovery mode is clean and repeatable.

### Where a firmware dump could still come from

`XMOS_DFU_SELECTIMAGE` exists in `atomdevice.dll`, so the bootloader can be pointed at a specific
image slot — plausibly what upload needs before it will yield anything.

**Do not probe for it by trial.** The XMOS vendor request block is `0xF0`–`0xF6` and includes
`XMOS_DFU_REVERTFACTORY` (`0xf1`), which overwrites the upgrade image. Guessing request numbers
next to that is how a working unit gets rolled back or bricked. The correct approach is to
disassemble `atomdevice.dll` around the `ClassOrVendorOutRequest(XMOS_DFU_SELECTIMAGE)` error
string and read the actual constant and its arguments out of the code.

## Open

1. The real `XMOS_DFU_SELECTIMAGE` request number and arguments, to be *read from
   `atomdevice.dll`*, never guessed. **[?]**
2. Whether upload yields anything once an image slot is selected. **[?]**
3. The runtime firmware-download URL Universal Control builds — it is not a static string in any
   binary. Capturing it means running UC against the device and watching the HTTP traffic. **[?]**
4. What the second MIDI port (`ATM SQ Control`) carries — a plausible candidate for the
   configuration and update channel Universal Control uses. **[?]**
