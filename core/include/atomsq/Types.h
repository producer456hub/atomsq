// Value types for the ATOM SQ surface.
#pragma once

#include <cstdint>
#include <string_view>

#include "atomsq/Protocol.h"

namespace atomsq {

// 7-bit RGB, the range the device actually accepts.
struct Color {
    std::uint8_t r = 0, g = 0, b = 0;

    constexpr Color() = default;
    constexpr Color(int red, int green, int blue) noexcept
        : r(clamp(red)), g(clamp(green)), b(clamp(blue)) {}

    // Convenience for callers thinking in conventional 0-255.
    static constexpr Color fromRgb8(int red, int green, int blue) noexcept {
        return Color{red >> 1, green >> 1, blue >> 1};
    }

    constexpr bool operator==(const Color& o) const noexcept {
        return r == o.r && g == o.g && b == o.b;
    }
    constexpr bool operator!=(const Color& o) const noexcept {
        return !(*this == o);
    }

    static constexpr std::uint8_t clamp(int v) noexcept {
        return static_cast<std::uint8_t>(v < 0 ? 0 : (v > 0x7F ? 0x7F : v));
    }
};

namespace colors {
inline constexpr Color kOff{0, 0, 0};
inline constexpr Color kWhite{0x7F, 0x7F, 0x7F};
inline constexpr Color kRed{0x7F, 0, 0};
inline constexpr Color kGreen{0, 0x7F, 0};
inline constexpr Color kBlue{0, 0, 0x7F};
inline constexpr Color kAmber{0x7F, 0x50, 0x00};
inline constexpr Color kCyan{0, 0x6A, 0x7F};
inline constexpr Color kMagenta{0x7F, 0, 0x5A};
}  // namespace colors

enum class Align : std::uint8_t { Center = 0, Left = 1, Right = 2 };

// Verified to compose with colour: an animating pad keeps its own hue.
enum class PadAnimation : std::uint8_t {
    None  = protocol::kPadLedOn,
    Blink = protocol::kPadLedBlink,
    Pulse = protocol::kPadLedPulse,
};

// The 14 screen cells: three soft-button columns above, two full-width lines
// through the middle, three columns below. Verified against the panel.
enum class Cell : std::uint8_t {
    Soft1Line1 = 0x0, Soft2Line1 = 0x1, Soft3Line1 = 0x2,
    Soft1Line2 = 0x3, Soft2Line2 = 0x4, Soft3Line2 = 0x5,
    MainLine1  = 0x6, MainLine2  = 0x7,
    Soft4Line1 = 0x8, Soft5Line1 = 0x9, Soft6Line1 = 0xA,
    Soft4Line2 = 0xB, Soft5Line2 = 0xC, Soft6Line2 = 0xD,
};

// True for the two full-width lines, which hold more text than a soft cell.
constexpr bool isMainLine(Cell cell) noexcept {
    return cell == Cell::MainLine1 || cell == Cell::MainLine2;
}

constexpr int cellCapacity(Cell cell) noexcept {
    return isMainLine(cell) ? protocol::kMainLineChars
                            : protocol::kSoftButtonChars;
}

// Every button that has a CC address. Note that having an address does not
// mean the host can light it — see LedKind.
enum class Button : std::uint8_t {
    A = 0x00, B = 0x01, C = 0x02, D = 0x03,
    E = 0x04, F = 0x05, G = 0x06, H = 0x07,
    Shift = 0x1F,
    Song = 0x20, Inst = 0x21, Editor = 0x22, User = 0x23,
    Soft1 = 0x24, Soft2 = 0x25, Soft3 = 0x26,
    Soft4 = 0x27, Soft5 = 0x28, Soft6 = 0x29,
    WheelLeft = 0x2A, WheelRight = 0x2B,
    SustainTouch = 0x40,
    Up = 0x57, Down = 0x59, Left = 0x5A, Right = 0x66,
    Metronome = 0x69, Record = 0x6B, Play = 0x6D, Stop = 0x6F,
};

// What a button's LED can actually do. Established by driving every button to
// green, then blue, then red, then all three at once, and reading the panel.
//
// Modelling this honestly matters: two thirds of the panel cannot show colour,
// and an API that accepts a Color for every button would silently do nothing
// on most of them.
enum class LedKind : std::uint8_t {
    Rgb,            // A-H and Play: took green, blue and red
    FixedRed,       // Record: ignores green and blue
    FixedBlue,      // Metronome: ignores green and red
    FirmwareOwned,  // the amber right-hand cluster; never responds to the host
};

constexpr LedKind ledKind(Button b) noexcept {
    switch (b) {
        case Button::A: case Button::B: case Button::C: case Button::D:
        case Button::E: case Button::F: case Button::G: case Button::H:
        case Button::Play:
            return LedKind::Rgb;
        case Button::Record:
            return LedKind::FixedRed;
        case Button::Metronome:
            return LedKind::FixedBlue;
        default:
            // Soft buttons, nav cluster, wheel arrows, Shift, mode column and
            // Stop all sit under the device's own menu UI.
            return LedKind::FirmwareOwned;
    }
}

constexpr bool supportsColor(Button b) noexcept {
    return ledKind(b) == LedKind::Rgb;
}

// The button CC addresses are sparse and non-contiguous — the transport and
// nav clusters sit on Mackie-ish numbers, which is a hint the firmware shares
// a control table with other PreSonus surfaces. So membership has to be tested
// explicitly rather than by a range check.
constexpr bool isKnownButton(std::uint8_t cc) noexcept {
    switch (static_cast<Button>(cc)) {
        case Button::A: case Button::B: case Button::C: case Button::D:
        case Button::E: case Button::F: case Button::G: case Button::H:
        case Button::Shift:
        case Button::Song: case Button::Inst:
        case Button::Editor: case Button::User:
        case Button::Soft1: case Button::Soft2: case Button::Soft3:
        case Button::Soft4: case Button::Soft5: case Button::Soft6:
        case Button::WheelLeft: case Button::WheelRight:
        case Button::SustainTouch:
        case Button::Up: case Button::Down:
        case Button::Left: case Button::Right:
        case Button::Metronome: case Button::Record:
        case Button::Play: case Button::Stop:
            return true;
    }
    return false;
}

// Host-controllable at all, even if only on/off.
constexpr bool isHostControllable(Button b) noexcept {
    return ledKind(b) != LedKind::FirmwareOwned;
}

enum class Encoder : std::uint8_t {
    Knob1 = 0x0E, Knob2 = 0x0F, Knob3 = 0x10, Knob4 = 0x11,
    Knob5 = 0x12, Knob6 = 0x13, Knob7 = 0x14, Knob8 = 0x15,
    Wheel = 0x1D,
};

// ---------------------------------------------------------------------------
// Input events
// ---------------------------------------------------------------------------

struct PadEvent {
    int index = 0;            // 0..31, note order; 0-15 is the lower row
    int velocity = 0;
    bool pressed = false;
};

struct PadPressureEvent {
    int index = 0;
    int pressure = 0;
};

struct FunctionPadEvent {
    bool plus = true;         // false = the minus pad
    int pressure = 0;
};

struct ButtonEvent {
    Button button{};
    bool pressed = false;
};

struct EncoderEvent {
    Encoder encoder{};
    // Speed-weighted, signed. NOT a tick count: these knobs have no detents,
    // so the magnitude reflects rotation speed and ramps as you turn faster.
    int delta = 0;
};

struct TouchStripEvent {
    int value = 0;            // 14-bit, 0..16383; springs back to 8192
};

}  // namespace atomsq
