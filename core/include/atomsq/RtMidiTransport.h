// RtMidi-backed transport.
//
// Optional: the core never references this. Build it when you want the library
// to open the device itself rather than being fed by a host that already has a
// MIDI connection.
#pragma once

#include <memory>
#include <string>
#include <vector>

#include "atomsq/Transport.h"

namespace atomsq {

class RtMidiTransport : public Transport {
public:
    RtMidiTransport();
    ~RtMidiTransport() override;

    // Port names as the OS reports them. Useful for diagnostics: Linux shows
    // the device's real USB string descriptors ("ATM SQ", "ATM SQ Control")
    // while Windows renames the second pair to MIDIIN2/MIDIOUT2.
    static std::vector<std::string> inputPorts();
    static std::vector<std::string> outputPorts();

    // Opens the first port pair whose name starts with `namePrefix`.
    //
    // The default is the control port. PreSonus's own .device file names
    // "ATM SQ" as its detectorPortName, and the second port has been silent
    // under every condition tested, so matching the bare name is correct even
    // though the other one is confusingly called "ATM SQ Control".
    bool open(const std::string& namePrefix = "ATM SQ");
    void close();
    bool isOpen() const { return open_; }

    void send(const std::uint8_t* data, std::size_t size) override;
    void poll() override;

    const std::string& lastError() const { return lastError_; }

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
    bool open_ = false;
    std::string lastError_;
};

}  // namespace atomsq
