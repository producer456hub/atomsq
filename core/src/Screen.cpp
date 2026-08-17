#include "atomsq/Screen.h"

namespace atomsq {

std::string Screen::fit(std::string_view text, Cell cell) {
    const auto capacity = static_cast<std::size_t>(cellCapacity(cell));
    if (text.size() <= capacity) return std::string{text};
    return std::string{text.substr(0, capacity)};
}

void Screen::setText(Cell cell, std::string_view text) {
    auto& state = at(cell);
    auto fitted = fit(text, cell);
    if (state.text == fitted) return;
    state.text = std::move(fitted);
    state.dirty = true;
}

void Screen::setColor(Cell cell, Color color) {
    auto& state = at(cell);
    if (state.color == color) return;
    state.color = color;
    state.dirty = true;
}

void Screen::setAlign(Cell cell, Align align) {
    auto& state = at(cell);
    if (state.align == align) return;
    state.align = align;
    state.dirty = true;
}

void Screen::set(Cell cell, std::string_view text, Color color, Align align) {
    setText(cell, text);
    setColor(cell, color);
    setAlign(cell, align);
}

void Screen::clearAll() {
    for (int i = 0; i < protocol::kCellCount; ++i)
        clear(static_cast<Cell>(i));
}

void Screen::invalidateAll() {
    for (auto& cell : cells_) cell.dirty = true;
}

int Screen::flush() {
    int written = 0;
    for (int i = 0; i < protocol::kCellCount; ++i) {
        auto cell = static_cast<Cell>(i);
        if (!at(cell).dirty) continue;
        write(cell);
        at(cell).dirty = false;
        ++written;
    }
    return written;
}

void Screen::write(Cell cell) {
    const auto& state = at(cell);

    ByteSpan message;
    message.reserve(11 + state.text.size());
    message.push_back(protocol::kSysExStart);
    for (auto byte : protocol::kManufacturer) message.push_back(byte);
    message.push_back(protocol::kModelAtomSQ);
    message.push_back(protocol::kCmdScreenWrite);
    message.push_back(static_cast<std::uint8_t>(cell));
    message.push_back(state.color.r);
    message.push_back(state.color.g);
    message.push_back(state.color.b);
    message.push_back(static_cast<std::uint8_t>(state.align));

    // SysEx data bytes must have the high bit clear. Icon glyphs are control
    // codes below 0x20 and pass through untouched; anything above 0x7F would
    // corrupt the stream, so it is masked rather than silently ending the
    // message.
    for (unsigned char ch : state.text)
        message.push_back(static_cast<std::uint8_t>(ch & 0x7F));

    message.push_back(protocol::kSysExEnd);
    transport_.send(message);
}

}  // namespace atomsq
