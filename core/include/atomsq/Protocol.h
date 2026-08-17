// ATOM SQ wire protocol constants.
//
// Every value here is verified against the hardware (serial ATSC20100175,
// firmware 1.17) or read out of PreSonus's own Studio One implementation.
// docs/PROTOCOL.md carries the provenance for each one; this header is the
// single place the numbers live so nothing can drift.
#pragma once

#include <cstdint>

namespace atomsq::protocol {

// ---------------------------------------------------------------------------
// MIDI status bytes
// ---------------------------------------------------------------------------

inline constexpr std::uint8_t kNoteOff      = 0x80;
inline constexpr std::uint8_t kNoteOn       = 0x90;
inline constexpr std::uint8_t kPolyPressure = 0xA0;
inline constexpr std::uint8_t kControlChange = 0xB0;
inline constexpr std::uint8_t kPitchBend    = 0xE0;

inline constexpr std::uint8_t kSysExStart = 0xF0;
inline constexpr std::uint8_t kSysExEnd   = 0xF7;

// ---------------------------------------------------------------------------
// Native mode
//
// The device boots standalone. A host claims the LEDs and screen with the ON
// message and MUST release with the OFF message; otherwise the unit is left
// waiting on a host that has gone away.
// ---------------------------------------------------------------------------

inline constexpr std::uint8_t kNativeOn[3]  = {kNoteOff | 0x0F, 0x00, 0x7F};
inline constexpr std::uint8_t kNativeOff[3] = {kNoteOff | 0x0F, 0x00, 0x00};

// ---------------------------------------------------------------------------
// SysEx
// ---------------------------------------------------------------------------

// PreSonus manufacturer id, then the model byte. Cross-checked against the
// FaderPort family, which uses the same 00 01 06 <model> shape (FP8 = 0x02,
// FP16 = 0x16).
inline constexpr std::uint8_t kManufacturer[3] = {0x00, 0x01, 0x06};
inline constexpr std::uint8_t kModelAtomSQ = 0x22;

inline constexpr std::uint8_t kCmdScreenWrite = 0x12;
inline constexpr std::uint8_t kCmdOwnership   = 0x13;  // effect unconfirmed
inline constexpr std::uint8_t kCmdNavCapture  = 0x14;  // verified

inline constexpr std::uint8_t kIdentityRequest[6] = {0xF0, 0x7E, 0x7F,
                                                     0x06, 0x01, 0xF7};

// ---------------------------------------------------------------------------
// Screen
// ---------------------------------------------------------------------------

inline constexpr int kCellCount = 14;

// The protocol accepts 50 bytes of text, but the panel shows far fewer and
// appends a single ellipsis glyph when it overflows. Truncating deliberately
// at these widths keeps control over what gets dropped.
inline constexpr int kMaxTextBytes    = 50;  // protocol cap
inline constexpr int kMainLineChars   = 25;  // measured; 26th cell is the ellipsis
inline constexpr int kSoftButtonChars = 7;   // measured; 8th cell is the ellipsis

// ---------------------------------------------------------------------------
// Pads
// ---------------------------------------------------------------------------

inline constexpr std::uint8_t kPadNoteStart = 0x24;  // pad[0][0], lower row
inline constexpr int kPadCount   = 32;
inline constexpr int kPadsPerRow = 16;

inline constexpr std::uint8_t kPadLedOff   = 0x00;
inline constexpr std::uint8_t kPadLedOn    = 0x7F;
inline constexpr std::uint8_t kPadLedBlink = 0x01;
inline constexpr std::uint8_t kPadLedPulse = 0x02;

// The ± function pads sit left of the grid and report pressure as poly
// aftertouch on these same pitches.
inline constexpr std::uint8_t kFunctionPadPlus  = 0x00;
inline constexpr std::uint8_t kFunctionPadMinus = 0x01;

// Global pad pressure, distinct from per-pad poly aftertouch.
inline constexpr std::uint8_t kPadPressureCC = 0x16;

// ---------------------------------------------------------------------------
// Colour
//
// The status *channel* selects which colour component a message carries, which
// is the single most surprising thing about this protocol: channel 1 is
// state/brightness, and channels 2/3/4 are red/green/blue at the same address.
// ---------------------------------------------------------------------------

inline constexpr std::uint8_t kChannelState = 0;
inline constexpr std::uint8_t kChannelRed   = 1;
inline constexpr std::uint8_t kChannelGreen = 2;
inline constexpr std::uint8_t kChannelBlue  = 3;

// ---------------------------------------------------------------------------
// Touch strip
// ---------------------------------------------------------------------------

inline constexpr std::uint8_t kStripLedStart = 55;  // CC 55..79
inline constexpr int kStripLedCount = 25;

// ---------------------------------------------------------------------------
// Encoders — relative, "signed plain"
//
// Verified: a slow clockwise turn sends 0x01 on every message, a slow
// counter-clockwise turn sends 0x41. Magnitude is the low 6 bits, bit 6 is the
// sign. The magnitude is speed-weighted, not a tick count — the knobs have no
// detents, so there is no tick to count.
// ---------------------------------------------------------------------------

inline constexpr std::uint8_t kEncoderSignBit = 0x40;

constexpr int decodeRelative(std::uint8_t value) noexcept {
    if (value == 0) return 0;
    if (value < kEncoderSignBit) return static_cast<int>(value);
    return -static_cast<int>(value - kEncoderSignBit);
}

// ---------------------------------------------------------------------------
// Private icon font
//
// Control codes render as glyphs rather than text. This is the only way to get
// non-alphanumeric symbols onto the screen — there is no bitmap path.
// ---------------------------------------------------------------------------

namespace icon {
inline constexpr char kArrowsUpDown     = '\x01';
inline constexpr char kArrowUp          = '\x02';
inline constexpr char kArrowDown        = '\x03';
inline constexpr char kArrowLeft        = '\x04';
inline constexpr char kArrowRight       = '\x05';
inline constexpr char kArrowDoubleLeft  = '\x06';
inline constexpr char kArrowDoubleRight = '\x07';
inline constexpr char kCircle           = '\x08';
inline constexpr char kDegree           = '\x09';
inline constexpr char kFolder           = '\x0A';
inline constexpr char kNote             = '\x0B';
inline constexpr char kPower            = '\x1B';
inline constexpr char kOk               = '\x1C';
inline constexpr char kClose            = '\x1D';
inline constexpr char kDotSmall         = '\x1E';
inline constexpr char kDotBig           = '\x1F';
}  // namespace icon

}  // namespace atomsq::protocol
