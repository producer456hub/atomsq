// MIDI transport abstraction.
//
// The core deliberately does not depend on RtMidi. Everything that builds
// messages is testable against a recording transport, and hosts that already
// own a MIDI stack (a DAW, a JUCE app) can feed the surface directly instead
// of opening a second connection to the same device.
#pragma once

#include <cstdint>
#include <functional>
#include <string>
#include <vector>

namespace atomsq {

using ByteSpan = std::vector<std::uint8_t>;

class Transport {
public:
    virtual ~Transport() = default;

    // Send one complete MIDI message.
    virtual void send(const std::uint8_t* data, std::size_t size) = 0;

    void send(const ByteSpan& bytes) { send(bytes.data(), bytes.size()); }

    // Pump any queued input, invoking the callback set by the Device. Hosts
    // driving the surface from their own MIDI thread can skip this and call
    // Device::handleMessage directly.
    virtual void poll() {}

    using MessageCallback = std::function<void(const std::uint8_t*, std::size_t)>;
    virtual void setCallback(MessageCallback cb) { callback_ = std::move(cb); }

protected:
    void deliver(const std::uint8_t* data, std::size_t size) {
        if (callback_) callback_(data, size);
    }

    MessageCallback callback_;
};

// Records everything sent. The core's test suite asserts exact byte sequences
// against docs/PROTOCOL.md through this, so the library can be verified with
// no hardware and no MIDI backend present.
class RecordingTransport : public Transport {
public:
    void send(const std::uint8_t* data, std::size_t size) override {
        sent.emplace_back(data, data + size);
    }

    void inject(const ByteSpan& message) {
        deliver(message.data(), message.size());
    }

    void clear() { sent.clear(); }

    std::vector<ByteSpan> sent;
};

}  // namespace atomsq
