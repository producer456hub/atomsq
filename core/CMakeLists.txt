cmake_minimum_required(VERSION 3.16)
project(atomsq_core LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# The core has no third-party dependencies on purpose. MIDI arrives through the
# Transport interface, so this library drops into a JUCE app, a DAW that
# already owns a MIDI connection, or a Rust caller behind a C ABI, without any
# of them inheriting a backend choice from us.
add_library(atomsq_core
    src/Device.cpp
    src/Screen.cpp
)
target_include_directories(atomsq_core PUBLIC include)

if(MSVC)
    target_compile_options(atomsq_core PRIVATE /W4)
else()
    target_compile_options(atomsq_core PRIVATE -Wall -Wextra -Wpedantic)
endif()

# ---------------------------------------------------------------------------
# Tests — no hardware, no MIDI backend. Byte-level assertions against
# docs/PROTOCOL.md through a recording transport.
# ---------------------------------------------------------------------------

enable_testing()
add_executable(atomsq_tests tests/test_core.cpp)
target_link_libraries(atomsq_tests PRIVATE atomsq_core)
add_test(NAME core COMMAND atomsq_tests)

# ---------------------------------------------------------------------------
# Optional RtMidi adapter and demo. Skipped cleanly when RtMidi is absent so
# the core still builds and tests anywhere.
# ---------------------------------------------------------------------------

find_package(PkgConfig QUIET)
if(PkgConfig_FOUND)
    pkg_check_modules(RTMIDI QUIET rtmidi)
endif()

if(RTMIDI_FOUND)
    add_library(atomsq_rtmidi src/RtMidiTransport.cpp)
    target_include_directories(atomsq_rtmidi PUBLIC include ${RTMIDI_INCLUDE_DIRS})
    target_link_libraries(atomsq_rtmidi PUBLIC atomsq_core ${RTMIDI_LIBRARIES})
    target_link_directories(atomsq_rtmidi PUBLIC ${RTMIDI_LIBRARY_DIRS})

    add_executable(atomsq_demo examples/demo.cpp)
    target_link_libraries(atomsq_demo PRIVATE atomsq_rtmidi)
    message(STATUS "RtMidi ${RTMIDI_VERSION} found — building adapter and demo")
else()
    message(STATUS "RtMidi not found — core and tests only")
endif()
