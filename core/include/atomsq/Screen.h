// The 14-cell text display.
//
// Cells are buffered and only emitted when something actually changed, which
// is what PreSonus's own implementation does. It matters more than it looks:
// a naive redraw of all 14 cells is ~14 SysEx messages of up to 56 bytes on a
// 31.25 kbaud-equivalent stream shared with note traffic, and it will audibly
// delay pad response.
#pragma once

#include <array>
#include <string>
#include <string_view>

#include "atomsq/Protocol.h"
#include "atomsq/Transport.h"
#include "atomsq/Types.h"

namespace atomsq {

class Screen {
public:
    explicit Screen(Transport& transport) : transport_(transport) {}

    // Set a cell's text. Truncated to the cell's real display width so we
    // choose what gets dropped rather than letting the panel append its own
    // ellipsis over the end of the string.
    void setText(Cell cell, std::string_view text);
    void setColor(Cell cell, Color color);
    void setAlign(Cell cell, Align align);

    // Set everything about a cell in one call.
    void set(Cell cell, std::string_view text, Color color,
             Align align = Align::Center);

    void clear(Cell cell) { setText(cell, {}); }
    void clearAll();

    // Emit SysEx for changed cells only. Returns how many were written, which
    // the tests use to prove the dirty-tracking actually suppresses redundant
    // traffic.
    int flush();

    // Force every cell out on the next flush, for reconnects — the device
    // loses its screen contents when native mode is released.
    void invalidateAll();

    std::string_view text(Cell cell) const { return at(cell).text; }
    Color color(Cell cell) const { return at(cell).color; }
    Align align(Cell cell) const { return at(cell).align; }

    // Truncation rule, exposed so callers can lay text out themselves.
    static std::string fit(std::string_view text, Cell cell);

private:
    struct CellState {
        std::string text;
        Color color = colors::kWhite;
        Align align = Align::Center;
        bool dirty = true;
    };

    static std::size_t indexOf(Cell cell) {
        return static_cast<std::size_t>(cell);
    }
    CellState& at(Cell cell) { return cells_[indexOf(cell)]; }
    const CellState& at(Cell cell) const { return cells_[indexOf(cell)]; }

    void write(Cell cell);

    Transport& transport_;
    std::array<CellState, protocol::kCellCount> cells_{};
};

}  // namespace atomsq
