HV P2P v26.10.01.04 - GITHUB READY SOURCE

PURPOSE
This is the direct successor to v26.10.01.03. It keeps the approved HV P2P
motion/safety architecture and closes the eight CTRL-TS/SRVR bench issues reported
against .03.

IMPORTANT
GitHub Actions is the authoritative native compiler. This source package does
NOT contain fabricated ESP32 application binaries, Windows executables or macOS
applications. The workflow builds CTRL-TS first, embeds that exact native image
and SHA into staged CTRL, then builds CTRL and W1P before creating matching SRVR
desktop artifacts and the Complete Release.

KEY v26.10.01.04 CHANGES
- AUX-assigned Limit/Winch calibration now advances an already-open wizard on each
  confirmed AUX press instead of reopening step 1. Joystick Calibration is now an
  AUX Assign option and follows the same open/advance behaviour.
- CTRL-TS keeps its original JPEG loading splash resident. If CTRL/SRVR connectivity
  is lost at runtime it returns to that same splash with "Waiting for SRVR" (or
  "Waiting for CTRL") and returns to the main UI when links recover, without reboot.
- CTRL-TS status/headings now use only glyphs supported by the compiled LVGL fonts.
  The square-box prefix and residual E-Stop leading slash are removed.
- macOS/Windows SRVR icon is updated to the approved dark/green CTRL-TS visual
  language with equal-size P2P / SRVR rows.
- Direct upgrade from older pre-beacon firmware such as v26.10.01.01 is bridged by
  SRVR asynchronously POSTing the exact already-SHA-verified bundled CTRL/W1P image
  to the node's existing /update/app endpoint. This is upgrade-only and does not
  downgrade a node reporting a newer release. Current firmware still uses the
  non-blocking UDP release-beacon/manifest authority path.
- CTRL joystick acquisition is reduced from a 50 ms / 8-sample / slow-IIR path to a
  25 ms / 5-sample trimmed mean with light low-latency filtering. SRVR live-state
  notification is also 25 ms. A full-scale input step reaches >96% of the filtered
  CTRL value within two control cycles while verified AI0/AI1 channel ownership is
  retained.
- Settings/Free-D auto-save, calibrated joystick Percentage, W1P 500 ms velocity
  watchdog, SRVR ~150 ms non-zero VEL keepalive, predictive stopping, hard limits,
  Servo Enable and E-stop protections are retained.

VERSION / BUILD IDENTITY
Application/release: 26.10.01.04
macOS short version: 26.10.1
macOS bundle build: 2610.1.4

FIRST COMMISSIONING
Use the GitHub-produced COMPLETE_RELEASE/FIRMWARE/STAGED_SOURCE folders for any
manual commissioning flash. Read:
- INITIAL_BOOTSTRAP_v26.10.01.04.md
- NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.10.01.04.md
- CTRL_JOYSTICK_WIRING_v26.10.01.04.md
- ARDUINO_IDE_SETTINGS_v26.10.01.04.md

Bench-check direct .01 -> .04 automatic convergence, all three AUX calibration
wizards, runtime SRVR-loss splash behaviour, E-Stop/source headings, and a rapid
0->100% joystick step before loaded motion commissioning.
