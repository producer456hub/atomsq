// Reference integration: own the whole panel and react to it.
//
// The C++ equivalent of probe/demo.py — paints all 14 screen cells with colour,
// alignment and icon glyphs, colours the pads with blink and pulse, runs the
// touch strip as a meter, and prints every input event.

#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <string>
#include <thread>

#include "atomsq/Device.h"
#include "atomsq/RtMidiTransport.h"

using namespace atomsq;
using namespace std::chrono_literals;

namespace {

Color hsv(float hue) {
    hue = hue - std::floor(hue);
    const int sector = static_cast<int>(hue * 6.0f) % 6;
    const float frac = hue * 6.0f - std::floor(hue * 6.0f);
    const int top = 0x7F;
    const int rising = static_cast<int>(0x7F * frac);
    const int falling = static_cast<int>(0x7F * (1.0f - frac));
    switch (sector) {
        case 0: return {top, rising, 0};
        case 1: return {falling, top, 0};
        case 2: return {0, top, rising};
        case 3: return {0, falling, top};
        case 4: return {rising, 0, top};
        default: return {top, 0, falling};
    }
}

void paintScreen(Screen& screen) {
    using namespace protocol::icon;

    // Six soft-button labels, title over value. Text is truncated to the cell's
    // real width (7 chars) so we choose the abbreviation rather than letting
    // the panel append an ellipsis over the end of it.
    struct Label { Cell title; Cell value; const char* name; std::string value_text; Color color; };
    const Label labels[] = {
        {Cell::Soft1Line1, Cell::Soft1Line2, "TRACK",
         std::string{kArrowLeft} + "Drums" + kArrowRight, colors::kAmber},
        {Cell::Soft2Line1, Cell::Soft2Line2, "DEVICE",
         std::string{kFolder} + "Bass", colors::kCyan},
        {Cell::Soft3Line1, Cell::Soft3Line2, "SCALE",
         std::string{kNote} + "Dmin", colors::kGreen},
        {Cell::Soft4Line1, Cell::Soft4Line2, "SWING", "56%", colors::kMagenta},
        {Cell::Soft5Line1, Cell::Soft5Line2, "LEN", "1/16", colors::kCyan},
        {Cell::Soft6Line1, Cell::Soft6Line2, "REC",
         std::string{kOk} + "ARM", colors::kRed},
    };
    for (const auto& label : labels) {
        screen.set(label.title, label.name, colors::kWhite);
        screen.set(label.value, label.value_text, label.color);
    }

    screen.set(Cell::MainLine1,
               std::string{kCircle} + " atomsq  " + kArrowsUpDown + " pattern 3",
               colors::kAmber, Align::Left);
    screen.set(Cell::MainLine2,
               std::string{"124.0 BPM 4/4 "} + kPower + " native",
               colors::kCyan, Align::Right);
}

void paintPads(Device& device) {
    // Lower row as a 16-step sequencer, upper row as accents. Two pads animate
    // so blink and pulse can be told apart — both keep their own colour.
    for (int step = 0; step < 16; ++step) {
        const bool accent = (step % 4) == 0;
        device.setPad(step, accent ? colors::kAmber : Color{0x20, 0x10, 0x00});
    }
    for (int step = 0; step < 16; ++step) {
        const int index = 16 + step;
        const Color color = (step % 2) ? colors::kCyan : colors::kMagenta;
        PadAnimation animation = PadAnimation::None;
        if (step == 4) animation = PadAnimation::Blink;
        else if (step == 12) animation = PadAnimation::Pulse;
        device.setPad(index, color, animation);
    }
}

const char* encoderName(Encoder encoder) {
    switch (encoder) {
        case Encoder::Knob1: return "knob1";
        case Encoder::Knob2: return "knob2";
        case Encoder::Knob3: return "knob3";
        case Encoder::Knob4: return "knob4";
        case Encoder::Knob5: return "knob5";
        case Encoder::Knob6: return "knob6";
        case Encoder::Knob7: return "knob7";
        case Encoder::Knob8: return "knob8";
        case Encoder::Wheel: return "wheel";
    }
    return "?";
}

}  // namespace

int main() {
    RtMidiTransport transport;
    if (!transport.open()) {
        std::printf("could not open the ATOM SQ: %s\n",
                    transport.lastError().c_str());
        std::printf("input ports seen:\n");
        for (const auto& name : RtMidiTransport::inputPorts())
            std::printf("  %s\n", name.c_str());
        return 1;
    }

    Device device(transport);
    device.blackout();
    paintScreen(device.screen());
    device.screen().flush();
    paintPads(device);

    for (auto button : {Button::A, Button::B, Button::C, Button::D})
        device.setButtonColor(button, colors::kAmber);
    for (auto button : {Button::E, Button::F, Button::G, Button::H})
        device.setButtonColor(button, colors::kCyan);
    device.setButtonBrightness(Button::Play, 127);

    Device::Callbacks callbacks;
    callbacks.pad = [](const PadEvent& e) {
        std::printf("pad %2d (%s row) %s vel %d\n", e.index,
                    e.index < 16 ? "lower" : "upper",
                    e.pressed ? "down" : "up", e.velocity);
    };
    callbacks.button = [](const ButtonEvent& e) {
        std::printf("button 0x%02X %s\n", static_cast<unsigned>(e.button),
                    e.pressed ? "pressed" : "released");
    };
    callbacks.encoder = [](const EncoderEvent& e) {
        std::printf("%s %+d\n", encoderName(e.encoder), e.delta);
    };
    callbacks.touchStrip = [](const TouchStripEvent& e) {
        std::printf("strip %d\n", e.value);
    };
    callbacks.unhandled = [](const std::uint8_t* data, std::size_t size) {
        std::printf("unhandled:");
        for (std::size_t i = 0; i < size; ++i) std::printf(" %02X", data[i]);
        std::printf("\n");
    };
    device.setCallbacks(callbacks);

    std::printf("panel painted; ctrl-c to stop\n");
    float meter = 0.0f;
    for (int tick = 0; tick < 2000; ++tick) {
        meter += 0.01f;
        if (meter > 1.0f) meter = 0.0f;
        device.setStripMeter(meter);
        device.poll();
        std::this_thread::sleep_for(30ms);
    }

    device.blackout();
    return 0;
}
