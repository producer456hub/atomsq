#include "atomsq/Device.h"

#include <algorithm>
#include <cmath>

namespace atomsq {
namespace {

constexpr bool inPadRange(int index) {
    return index >= 0 && index < protocol::kPadCount;
}

}  // namespace

Device::Device(Transport& transport)
    : transport_(transport), screen_(transport) {
    transport_.setCallback([this](const std::uint8_t* data, std::size_t size) {
        handleMessage(data, size);
    });
    sendNative(true);
}

Device::~Device() {
    // Release even if the caller is unwinding. A device left in native mode
    // with no host is unresponsive until it is replugged.
    sendNative(false);
}

void Device::sendNative(bool on) {
    const auto* msg = on ? protocol::kNativeOn : protocol::kNativeOff;
    transport_.send(msg, 3);
}

void Device::send3(std::uint8_t status, std::uint8_t data1, std::uint8_t data2) {
    const std::uint8_t message[3] = {status, data1, data2};
    transport_.send(message, 3);
}

void Device::sendSysExCommand(std::uint8_t command, std::uint8_t argument) {
    ByteSpan message;
    message.push_back(protocol::kSysExStart);
    for (auto byte : protocol::kManufacturer) message.push_back(byte);
    message.push_back(protocol::kModelAtomSQ);
    message.push_back(command);
    message.push_back(argument);
    message.push_back(protocol::kSysExEnd);
    transport_.send(message);
}

// ---------------------------------------------------------------------------
// Pads
// ---------------------------------------------------------------------------

void Device::sendPadState(int index) {
    const auto note = static_cast<std::uint8_t>(protocol::kPadNoteStart + index);
    const auto& pad = pads_[static_cast<std::size_t>(index)];
    const std::uint8_t value =
        pad.lit ? static_cast<std::uint8_t>(pad.animation) : protocol::kPadLedOff;
    send3(protocol::kNoteOn | protocol::kChannelState, note, value);
}

void Device::setPadColor(int index, Color color) {
    if (!inPadRange(index)) return;
    auto& pad = pads_[static_cast<std::size_t>(index)];
    pad.color = color;

    const auto note = static_cast<std::uint8_t>(protocol::kPadNoteStart + index);
    send3(protocol::kNoteOn | protocol::kChannelRed, note, color.r);
    send3(protocol::kNoteOn | protocol::kChannelGreen, note, color.g);
    send3(protocol::kNoteOn | protocol::kChannelBlue, note, color.b);
}

void Device::setPadAnimation(int index, PadAnimation animation) {
    if (!inPadRange(index)) return;
    auto& pad = pads_[static_cast<std::size_t>(index)];
    pad.animation = animation;
    pad.lit = true;
    sendPadState(index);
}

void Device::setPad(int index, Color color, PadAnimation animation) {
    if (!inPadRange(index)) return;
    setPadColor(index, color);
    setPadAnimation(index, animation);
}

void Device::clearPad(int index) {
    if (!inPadRange(index)) return;
    pads_[static_cast<std::size_t>(index)].lit = false;
    sendPadState(index);
}

void Device::clearPads() {
    for (int i = 0; i < protocol::kPadCount; ++i) clearPad(i);
}

// ---------------------------------------------------------------------------
// Buttons
// ---------------------------------------------------------------------------

void Device::setButtonColor(Button button, Color color) {
    // Silently doing nothing here would be worse than doing nothing loudly:
    // the caller can ask supportsColor() and pick a different affordance.
    if (!supportsColor(button)) return;

    const auto cc = static_cast<std::uint8_t>(button);
    send3(protocol::kControlChange | protocol::kChannelRed, cc, color.r);
    send3(protocol::kControlChange | protocol::kChannelGreen, cc, color.g);
    send3(protocol::kControlChange | protocol::kChannelBlue, cc, color.b);
}

void Device::setButtonBrightness(Button button, int brightness) {
    if (!isHostControllable(button)) return;
    const auto value = Color::clamp(brightness);
    send3(protocol::kControlChange, static_cast<std::uint8_t>(button), value);
}

void Device::clearButtons() {
    static constexpr Button kAll[] = {
        Button::A, Button::B, Button::C, Button::D,
        Button::E, Button::F, Button::G, Button::H,
        Button::Play, Button::Record, Button::Metronome,
    };
    for (auto button : kAll) setButtonBrightness(button, 0);
}

// ---------------------------------------------------------------------------
// Touch strip
// ---------------------------------------------------------------------------

void Device::setStripMeter(float value) {
    value = std::clamp(value, 0.0f, 1.0f);
    const int top = static_cast<int>(
        std::lround(value * (protocol::kStripLedCount - 1)));
    for (int i = 0; i < protocol::kStripLedCount; ++i) {
        const std::uint8_t level = (i <= top) ? 127 : 0;
        if (strip_[static_cast<std::size_t>(i)] == level) continue;
        strip_[static_cast<std::size_t>(i)] = level;
        send3(protocol::kControlChange,
              static_cast<std::uint8_t>(protocol::kStripLedStart + i), level);
    }
}

void Device::setStripCursor(float value) {
    value = std::clamp(value, 0.0f, 1.0f);
    const int lit = static_cast<int>(
        std::lround(value * (protocol::kStripLedCount - 1)));
    for (int i = 0; i < protocol::kStripLedCount; ++i) {
        const std::uint8_t level = (i == lit) ? 127 : 0;
        if (strip_[static_cast<std::size_t>(i)] == level) continue;
        strip_[static_cast<std::size_t>(i)] = level;
        send3(protocol::kControlChange,
              static_cast<std::uint8_t>(protocol::kStripLedStart + i), level);
    }
}

void Device::clearStrip() {
    for (int i = 0; i < protocol::kStripLedCount; ++i) {
        if (strip_[static_cast<std::size_t>(i)] == 0) continue;
        strip_[static_cast<std::size_t>(i)] = 0;
        send3(protocol::kControlChange,
              static_cast<std::uint8_t>(protocol::kStripLedStart + i), 0);
    }
}

// ---------------------------------------------------------------------------
// Modes
// ---------------------------------------------------------------------------

void Device::setNavKeyCapture(bool hostOwns) {
    sendSysExCommand(protocol::kCmdNavCapture, hostOwns ? 0x01 : 0x00);
}

void Device::setPanelOwnership(bool hostOwns) {
    sendSysExCommand(protocol::kCmdOwnership, hostOwns ? 0x01 : 0x00);
}

void Device::requestIdentity() {
    transport_.send(protocol::kIdentityRequest, sizeof(protocol::kIdentityRequest));
}

void Device::blackout() {
    clearPads();
    clearButtons();
    clearStrip();
    screen_.clearAll();
    screen_.flush();
}

// ---------------------------------------------------------------------------
// Input
// ---------------------------------------------------------------------------

void Device::handleMessage(const std::uint8_t* data, std::size_t size) {
    if (size < 3 || data[0] == protocol::kSysExStart) {
        if (callbacks_.unhandled) callbacks_.unhandled(data, size);
        return;
    }

    const std::uint8_t status = data[0] & 0xF0;
    const std::uint8_t d1 = data[1];
    const std::uint8_t d2 = data[2];

    switch (status) {
        case protocol::kNoteOn:
        case protocol::kNoteOff: {
            // Pads arrive on channel 10, not channel 1 — the reverse of the
            // channel their LEDs live on. Channel is deliberately not checked
            // so a remapped device still works.
            if (d1 == protocol::kFunctionPadPlus || d1 == protocol::kFunctionPadMinus) {
                if (callbacks_.functionPad)
                    callbacks_.functionPad({d1 == protocol::kFunctionPadPlus,
                                            status == protocol::kNoteOn ? d2 : 0});
                return;
            }
            const int index = d1 - protocol::kPadNoteStart;
            if (!inPadRange(index)) break;
            const bool pressed = (status == protocol::kNoteOn) && d2 > 0;
            if (callbacks_.pad) callbacks_.pad({index, d2, pressed});
            return;
        }

        case protocol::kPolyPressure: {
            if (d1 == protocol::kFunctionPadPlus || d1 == protocol::kFunctionPadMinus) {
                if (callbacks_.functionPad)
                    callbacks_.functionPad({d1 == protocol::kFunctionPadPlus, d2});
                return;
            }
            const int index = d1 - protocol::kPadNoteStart;
            if (!inPadRange(index)) break;
            if (callbacks_.padPressure) callbacks_.padPressure({index, d2});
            return;
        }

        case protocol::kPitchBend: {
            const int value = d1 | (d2 << 7);
            if (callbacks_.touchStrip) callbacks_.touchStrip({value});
            return;
        }

        case protocol::kControlChange: {
            switch (static_cast<Encoder>(d1)) {
                case Encoder::Knob1: case Encoder::Knob2: case Encoder::Knob3:
                case Encoder::Knob4: case Encoder::Knob5: case Encoder::Knob6:
                case Encoder::Knob7: case Encoder::Knob8: case Encoder::Wheel:
                    if (callbacks_.encoder)
                        callbacks_.encoder({static_cast<Encoder>(d1),
                                            protocol::decodeRelative(d2)});
                    return;
                default:
                    break;
            }
            if (isKnownButton(d1)) {
                if (callbacks_.button)
                    callbacks_.button({static_cast<Button>(d1), d2 >= 64});
                return;
            }
            break;
        }

        default:
            break;
    }

    if (callbacks_.unhandled) callbacks_.unhandled(data, size);
}

}  // namespace atomsq
