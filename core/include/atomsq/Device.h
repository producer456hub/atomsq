// The ATOM SQ surface: LEDs out, events in.
//
// Owning the device means claiming native mode, which the device cannot detect
// the end of on its own — if a host exits without releasing it, the unit sits
// waiting for a host that is gone. Device therefore releases in its destructor,
// including on an exception path.
#pragma once

#include <array>
#include <functional>
#include <memory>

#include "atomsq/Protocol.h"
#include "atomsq/Screen.h"
#include "atomsq/Transport.h"
#include "atomsq/Types.h"

namespace atomsq {

class Device {
public:
    // Claims native mode immediately. The transport must outlive the Device.
    explicit Device(Transport& transport);
    ~Device();

    Device(const Device&) = delete;
    Device& operator=(const Device&) = delete;

    Screen& screen() { return screen_; }

    // -- pads -------------------------------------------------------------
    //
    // index 0..31 in note order: 0-15 is the lower (numbered) row, 16-31 the
    // upper row. Colour and animation are independent — an animating pad keeps
    // its own hue.

    void setPadColor(int index, Color color);
    void setPadAnimation(int index, PadAnimation animation);
    void setPad(int index, Color color, PadAnimation animation = PadAnimation::None);
    void clearPad(int index);
    void clearPads();

    // -- buttons ----------------------------------------------------------
    //
    // Only nine buttons take colour and only eleven respond to the host at
    // all. These calls are no-ops on buttons the firmware owns rather than
    // pretending to have worked — query with supportsColor()/isHostControllable().

    void setButtonColor(Button button, Color color);
    void setButtonBrightness(Button button, int brightness);
    void clearButtons();

    // -- touch strip ------------------------------------------------------

    // Light every LED up to `value` (0.0-1.0), like a meter.
    void setStripMeter(float value);
    // Light exactly one LED, like a cursor.
    void setStripCursor(float value);
    void clearStrip();

    // -- modes ------------------------------------------------------------

    // Stop the nav keys emitting MIDI so the host can own the arrow cluster.
    // Verified: with this set the nav keys go silent while other controls keep
    // transmitting.
    void setNavKeyCapture(bool hostOwns);

    // Community-reported display/button-light ownership. Confirmed NOT to hand
    // over the firmware-owned amber cluster, at least in this ordering. Exposed
    // because it is part of the protocol, not because it is known to be useful.
    void setPanelOwnership(bool hostOwns);

    void requestIdentity();

    // Everything off. Worth calling before release so the panel does not keep
    // showing stale state.
    void blackout();

    // -- input ------------------------------------------------------------

    struct Callbacks {
        std::function<void(const PadEvent&)> pad;
        std::function<void(const PadPressureEvent&)> padPressure;
        std::function<void(const FunctionPadEvent&)> functionPad;
        std::function<void(const ButtonEvent&)> button;
        std::function<void(const EncoderEvent&)> encoder;
        std::function<void(const TouchStripEvent&)> touchStrip;
        // Anything the parser could not attribute. If this fires, the protocol
        // model has a hole in it — worth surfacing rather than swallowing.
        std::function<void(const std::uint8_t*, std::size_t)> unhandled;
    };

    void setCallbacks(Callbacks callbacks) { callbacks_ = std::move(callbacks); }

    // Pump the transport. Hosts with their own MIDI thread can bypass this and
    // call handleMessage directly.
    void poll() { transport_.poll(); }
    void handleMessage(const std::uint8_t* data, std::size_t size);

private:
    void sendNative(bool on);
    void sendSysExCommand(std::uint8_t command, std::uint8_t argument);
    void sendPadState(int index);
    void send3(std::uint8_t status, std::uint8_t data1, std::uint8_t data2);

    struct PadState {
        Color color = colors::kWhite;
        PadAnimation animation = PadAnimation::None;
        bool lit = false;
    };

    Transport& transport_;
    Screen screen_;
    Callbacks callbacks_;
    std::array<PadState, protocol::kPadCount> pads_{};
    std::array<std::uint8_t, protocol::kStripLedCount> strip_{};
};

}  // namespace atomsq
