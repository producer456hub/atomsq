// Byte-level tests for the ATOM SQ core.
//
// These assert the exact messages the library puts on the wire against
// docs/PROTOCOL.md. Everything here runs with no hardware and no MIDI backend,
// so a regression in message construction is caught at build time rather than
// by squinting at a panel.

#include <cstdio>
#include <string>
#include <vector>

#include "atomsq/Device.h"
#include "atomsq/Transport.h"

using namespace atomsq;

namespace {

int g_failures = 0;
int g_checks = 0;

std::string hex(const ByteSpan& bytes) {
    static const char* digits = "0123456789ABCDEF";
    std::string out;
    for (auto byte : bytes) {
        out += digits[byte >> 4];
        out += digits[byte & 0x0F];
        out += ' ';
    }
    if (!out.empty()) out.pop_back();
    return out;
}

void check(bool condition, const std::string& what) {
    ++g_checks;
    if (condition) return;
    ++g_failures;
    std::printf("  FAIL: %s\n", what.c_str());
}

void expectMessage(const ByteSpan& actual, const ByteSpan& expected,
                   const std::string& what) {
    ++g_checks;
    if (actual == expected) return;
    ++g_failures;
    std::printf("  FAIL: %s\n    expected: %s\n    actual:   %s\n",
                what.c_str(), hex(expected).c_str(), hex(actual).c_str());
}

// --------------------------------------------------------------------------

void testNativeModeLifecycle() {
    std::printf("native mode lifecycle\n");
    RecordingTransport transport;
    {
        Device device(transport);
        expectMessage(transport.sent.at(0), {0x8F, 0x00, 0x7F},
                      "claims native mode on construction");
    }
    // The release must happen even though nothing asked for it: a device left
    // in native mode with no host is unresponsive until replugged.
    expectMessage(transport.sent.back(), {0x8F, 0x00, 0x00},
                  "releases native mode on destruction");
}

void testScreenMessageShape() {
    std::printf("screen message shape\n");
    RecordingTransport transport;
    Device device(transport);

    // Cells start dirty on purpose: after claiming native mode the panel's
    // contents are undefined, so the first flush must paint all 14 rather than
    // assume the screen is blank.
    check(device.screen().flush() == protocol::kCellCount,
          "first flush paints every cell");
    transport.clear();

    device.screen().set(Cell::MainLine1, "Hi", colors::kAmber, Align::Left);
    const int written = device.screen().flush();
    check(written == 1, "flush writes only the changed cell");

    // F0 00 01 06 22 12 <cell> <r> <g> <b> <align> 'H' 'i' F7
    expectMessage(transport.sent.at(0),
                  {0xF0, 0x00, 0x01, 0x06, 0x22, 0x12, 0x06,
                   0x7F, 0x50, 0x00, 0x01, 'H', 'i', 0xF7},
                  "screen write matches the documented layout");
}

void testScreenDirtyTracking() {
    std::printf("screen dirty tracking\n");
    RecordingTransport transport;
    Device device(transport);
    device.screen().flush();  // clear the initial all-dirty state
    transport.clear();

    device.screen().setText(Cell::MainLine1, "same");
    check(device.screen().flush() == 1, "first write is emitted");
    transport.clear();

    device.screen().setText(Cell::MainLine1, "same");
    check(device.screen().flush() == 0, "identical text emits nothing");
    check(transport.sent.empty(), "no traffic for an unchanged cell");

    device.screen().invalidateAll();
    check(device.screen().flush() == protocol::kCellCount,
          "invalidateAll re-emits every cell");
}

void testScreenTruncation() {
    std::printf("screen truncation\n");
    const std::string ruler = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvw";

    // Measured on hardware: 25 characters on a main line, 7 in a soft cell,
    // after which the device appends its own ellipsis glyph.
    check(Screen::fit(ruler, Cell::MainLine1).size() == 25,
          "main line truncates at 25 characters");
    check(Screen::fit(ruler, Cell::Soft1Line1).size() == 7,
          "soft cell truncates at 7 characters");
    check(Screen::fit("short", Cell::MainLine1) == "short",
          "text within capacity is untouched");
}

void testPadColourUsesStatusChannel() {
    std::printf("pad colour\n");
    RecordingTransport transport;
    Device device(transport);
    transport.clear();

    device.setPadColor(0, Color{0x11, 0x22, 0x33});
    // Colour is selected by the status channel, at the same note address.
    expectMessage(transport.sent.at(0), {0x91, 0x24, 0x11}, "red on channel 2");
    expectMessage(transport.sent.at(1), {0x92, 0x24, 0x22}, "green on channel 3");
    expectMessage(transport.sent.at(2), {0x93, 0x24, 0x33}, "blue on channel 4");
}

void testPadAnimationComposesWithColour() {
    std::printf("pad animation\n");
    RecordingTransport transport;
    Device device(transport);
    transport.clear();

    device.setPad(31, colors::kCyan, PadAnimation::Pulse);
    // Last pad of the upper row: 0x24 + 31 = 0x43.
    expectMessage(transport.sent.back(), {0x90, 0x43, 0x02},
                  "pulse state on channel 1, colour left intact");

    transport.clear();
    device.clearPad(31);
    expectMessage(transport.sent.at(0), {0x90, 0x43, 0x00}, "pad off");
}

void testButtonLedKindsAreHonest() {
    std::printf("button LED classes\n");
    check(supportsColor(Button::A), "A-H are RGB");
    check(supportsColor(Button::Play), "Play is RGB");
    check(!supportsColor(Button::Record), "Record is fixed red");
    check(!supportsColor(Button::Metronome), "Metronome is fixed blue");
    check(!supportsColor(Button::Soft1), "soft buttons are firmware-owned");
    check(!isHostControllable(Button::Up), "nav cluster is firmware-owned");
    check(isHostControllable(Button::Record), "Record still takes on/off");

    RecordingTransport transport;
    Device device(transport);
    transport.clear();

    device.setButtonColor(Button::A, colors::kGreen);
    expectMessage(transport.sent.at(0), {0xB1, 0x00, 0x00}, "button red");
    expectMessage(transport.sent.at(1), {0xB2, 0x00, 0x7F}, "button green");
    expectMessage(transport.sent.at(2), {0xB3, 0x00, 0x00}, "button blue");

    transport.clear();
    // Writing colour to a firmware-owned button must not put bytes on the wire
    // that the device will ignore.
    device.setButtonColor(Button::Soft1, colors::kGreen);
    check(transport.sent.empty(), "colour to a firmware-owned button is dropped");
}

void testEncoderDecode() {
    std::printf("encoder decode\n");
    // Verified on hardware: slow clockwise sends 0x01, slow counter-clockwise
    // sends 0x41.
    check(protocol::decodeRelative(0x01) == 1, "0x01 is +1");
    check(protocol::decodeRelative(0x41) == -1, "0x41 is -1");
    check(protocol::decodeRelative(0x20) == 32, "0x20 is +32");
    check(protocol::decodeRelative(0x60) == -32, "0x60 is -32");
    check(protocol::decodeRelative(0x00) == 0, "0x00 is no movement");

    RecordingTransport transport;
    Device device(transport);
    int delta = 0;
    Encoder which{};
    Device::Callbacks callbacks;
    callbacks.encoder = [&](const EncoderEvent& e) {
        which = e.encoder;
        delta = e.delta;
    };
    device.setCallbacks(callbacks);

    transport.inject({0xB0, 0x0E, 0x41});
    check(which == Encoder::Knob1 && delta == -1,
          "knob 1 counter-clockwise decodes to -1");
}

void testPadInputArrivesOnChannel10() {
    std::printf("pad input\n");
    RecordingTransport transport;
    Device device(transport);

    PadEvent got{};
    bool fired = false;
    Device::Callbacks callbacks;
    callbacks.pad = [&](const PadEvent& e) { got = e; fired = true; };
    device.setCallbacks(callbacks);

    // Pads transmit on channel 10 while their LEDs live on channel 1.
    transport.inject({0x99, 0x30, 0x64});
    check(fired, "channel 10 note is recognised as a pad");
    check(got.index == 12, "note 0x30 is pad index 12");
    check(got.pressed && got.velocity == 0x64, "velocity is carried through");
}

void testUnhandledIsSurfaced() {
    std::printf("unhandled messages\n");
    RecordingTransport transport;
    Device device(transport);

    bool sawUnhandled = false;
    Device::Callbacks callbacks;
    callbacks.unhandled = [&](const std::uint8_t*, std::size_t) {
        sawUnhandled = true;
    };
    device.setCallbacks(callbacks);

    // A CC that belongs to nothing we know about must not be swallowed - if
    // this ever fires in the field, the protocol model has a hole in it.
    transport.inject({0xB0, 0x7A, 0x01});
    check(sawUnhandled, "unknown CC reaches the unhandled callback");
}

void testNavCaptureCommand() {
    std::printf("nav-key capture\n");
    RecordingTransport transport;
    Device device(transport);
    transport.clear();

    device.setNavKeyCapture(true);
    expectMessage(transport.sent.at(0),
                  {0xF0, 0x00, 0x01, 0x06, 0x22, 0x14, 0x01, 0xF7},
                  "nav capture on");
    device.setNavKeyCapture(false);
    expectMessage(transport.sent.at(1),
                  {0xF0, 0x00, 0x01, 0x06, 0x22, 0x14, 0x00, 0xF7},
                  "nav capture off");
}

void testStripMeterIsIncremental() {
    std::printf("touch strip\n");
    RecordingTransport transport;
    Device device(transport);
    transport.clear();

    device.setStripMeter(0.0f);
    const auto firstCount = transport.sent.size();
    check(firstCount == 1, "only LED 0 changes when meter starts at zero");
    expectMessage(transport.sent.at(0), {0xB0, 0x37, 0x7F}, "strip LED 0 on");

    transport.clear();
    device.setStripMeter(0.0f);
    check(transport.sent.empty(), "re-setting the same level sends nothing");
}

}  // namespace

int main() {
    std::printf("atomsq core tests\n\n");
    testNativeModeLifecycle();
    testScreenMessageShape();
    testScreenDirtyTracking();
    testScreenTruncation();
    testPadColourUsesStatusChannel();
    testPadAnimationComposesWithColour();
    testButtonLedKindsAreHonest();
    testEncoderDecode();
    testPadInputArrivesOnChannel10();
    testUnhandledIsSurfaced();
    testNavCaptureCommand();
    testStripMeterIsIncremental();

    std::printf("\n%d checks, %d failures\n", g_checks, g_failures);
    return g_failures == 0 ? 0 : 1;
}
