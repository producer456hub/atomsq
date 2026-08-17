#include "atomsq/RtMidiTransport.h"

#include <RtMidi.h>

#include <algorithm>

namespace atomsq {

struct RtMidiTransport::Impl {
    RtMidiIn in;
    RtMidiOut out;
    std::vector<unsigned char> scratch;
};

RtMidiTransport::RtMidiTransport() : impl_(std::make_unique<Impl>()) {}

RtMidiTransport::~RtMidiTransport() { close(); }

std::vector<std::string> RtMidiTransport::inputPorts() {
    std::vector<std::string> names;
    try {
        RtMidiIn in;
        for (unsigned i = 0; i < in.getPortCount(); ++i)
            names.push_back(in.getPortName(i));
    } catch (const RtMidiError&) {
        // An absent or misconfigured MIDI backend is a normal condition on a
        // headless box; report it as "no ports" rather than throwing.
    }
    return names;
}

std::vector<std::string> RtMidiTransport::outputPorts() {
    std::vector<std::string> names;
    try {
        RtMidiOut out;
        for (unsigned i = 0; i < out.getPortCount(); ++i)
            names.push_back(out.getPortName(i));
    } catch (const RtMidiError&) {
    }
    return names;
}

bool RtMidiTransport::open(const std::string& namePrefix) {
    close();
    try {
        int inIndex = -1, outIndex = -1;
        for (unsigned i = 0; i < impl_->in.getPortCount(); ++i) {
            if (impl_->in.getPortName(i).rfind(namePrefix, 0) == 0) {
                inIndex = static_cast<int>(i);
                break;
            }
        }
        for (unsigned i = 0; i < impl_->out.getPortCount(); ++i) {
            if (impl_->out.getPortName(i).rfind(namePrefix, 0) == 0) {
                outIndex = static_cast<int>(i);
                break;
            }
        }
        if (inIndex < 0 || outIndex < 0) {
            lastError_ = "no port starting with \"" + namePrefix + "\"";
            return false;
        }

        impl_->in.openPort(static_cast<unsigned>(inIndex));
        // SysEx is filtered out by default and we need identity replies.
        impl_->in.ignoreTypes(false, true, true);
        impl_->out.openPort(static_cast<unsigned>(outIndex));
        open_ = true;
        return true;
    } catch (const RtMidiError& error) {
        lastError_ = error.getMessage();
        return false;
    }
}

void RtMidiTransport::close() {
    if (!open_) return;
    try {
        impl_->in.closePort();
        impl_->out.closePort();
    } catch (const RtMidiError&) {
    }
    open_ = false;
}

void RtMidiTransport::send(const std::uint8_t* data, std::size_t size) {
    if (!open_) return;
    try {
        impl_->out.sendMessage(data, size);
    } catch (const RtMidiError& error) {
        lastError_ = error.getMessage();
    }
}

void RtMidiTransport::poll() {
    if (!open_) return;
    for (;;) {
        impl_->scratch.clear();
        double stamp = impl_->in.getMessage(&impl_->scratch);
        (void)stamp;
        if (impl_->scratch.empty()) return;
        deliver(impl_->scratch.data(), impl_->scratch.size());
    }
}

}  // namespace atomsq
