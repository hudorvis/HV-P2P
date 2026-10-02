HV P2P v26.10.02.02 - GITHUB READY SOURCE

PURPOSE
This is the direct successor to v26.10.02.01. It keeps the approved HV P2P
motion/safety architecture and closes the intermittent CTRL-TS calibration
render/reset issue captured in the 2 October bench videos.

IMPORTANT
GitHub Actions is the authoritative native compiler. This source package does
NOT contain fabricated ESP32 application binaries, Windows executables or macOS
applications. The workflow builds CTRL-TS first, embeds that exact native image
and SHA into staged CTRL, then builds CTRL and W1P before creating matching SRVR
desktop artifacts and the Complete Release.

KEY v26.10.02.02 CHANGES
- One CTRL-TS firmware dashboard shows W1P, CTRL and CTRL-TS update phase/percent.
- Local CTRL-TS OTA is hardened against the observed RGB shift: no LVGL mutex
  across flash blocks, dashboard rendered before flash, 6 MHz update PCLK, RGB
  stream re-alignment after blocks, and a 20-line Waveshare bounce buffer in CI.
- Calibration display ownership is now edge-triggered: no repeated foreground
  moves, no hidden Drive/Speed/Position redraws under the wizard, and no redundant
  explicit label invalidation.
- Joystick step 1 reads `Hold Joystick Left, then press Confirm`; the lower AUX
  instruction row is removed.
- CTRL-TS retains ESP reset-reason logging so any recurrence can be classified.
- v26.10.01.04 runtime splash/status/glyph/legacy OTA and low-latency joystick
  fixes, plus .03 auto-save and calibrated percentage behaviour, are retained.

VERSION / BUILD IDENTITY
Application/release: 26.10.02.02
macOS short version: 26.10.2
macOS bundle build: 2610.2.2

FIRST COMMISSIONING
Use the GitHub-produced COMPLETE_RELEASE/FIRMWARE/STAGED_SOURCE folders for any
manual commissioning flash. Read:
- INITIAL_BOOTSTRAP_v26.10.02.02.md
- NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.10.02.02.md
- CTRL_JOYSTICK_WIRING_v26.10.02.02.md
- ARDUINO_IDE_SETTINGS_v26.10.02.02.md

Bench-check the unified W1P/CTRL/CTRL-TS firmware dashboard, visually stable
CTRL-TS local OTA, all three AUX calibration wizards, runtime SRVR-loss splash,
and rapid joystick response before loaded motion commissioning.
