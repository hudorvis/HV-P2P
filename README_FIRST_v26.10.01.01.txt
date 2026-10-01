HV P2P v26.10.01.01 - GITHUB READY SOURCE

PURPOSE
This is the direct bug-fix successor to the authoritative v26.09.29.06 source.
It preserves the approved .06 UI and motion/safety feature set while closing the
reported CTRL analogue-channel, status/calibration, joystick-direction and
CTRL-TS firmware-update display defects.

IMPORTANT
GitHub Actions is the authoritative native compiler. This source package does
NOT contain fabricated ESP32 application binaries, Windows executables or macOS
applications. The workflow builds CTRL-TS first, embeds that exact native image
and SHA into staged CTRL, then builds CTRL and W1P before creating the matching
SRVR desktop artifacts and Complete Release.

KEY v26.10.01.01 CHANGES
- AI0 E-stop and AI1 joystick reads are explicit verified SGM58031 transactions;
  AI1 restoration is guaranteed after AI0 sampling attempts.
- Physical CTRL E-stop identity is separated from CTRL-TS/firmware safety faults.
- Position reference never survives a new SRVR session and is invalidated by a
  W1P reboot/session change; Limit Calibration or Slip establishes it again.
- System status priority is red safety/fault first, yellow System Un-Calibrated
  second, and green System Ready only when both safety and reference are valid.
- Missing/unsafe W1P remains visible as a safety source, including in Virtual
  Position Source mode.
- Joystick electrical polarity is corrected at CTRL so physical Left/Right,
  Value/Percentage, requested speed and limit direction use one sign convention.
- CTRL-TS runtime OTA owns a stable dedicated update screen showing connection
  state and progress; normal UI timers cannot overwrite it while update is active.
- All v26.09.29.06 centre-drift, predictive stopping, preset-name, watchdog,
  RS485, Leadshine and hard-limit protections are retained.

VERSION / BUILD IDENTITY
Application/release: 26.10.01.01
macOS short version: 26.10.1
macOS bundle build: 2610.1.1

FIRST COMMISSIONING
Use the GitHub-produced COMPLETE_RELEASE/FIRMWARE/STAGED_SOURCE folders for any
manual commissioning flash. Read:
- INITIAL_BOOTSTRAP_v26.10.01.01.md
- NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.10.01.01.md
- CTRL_JOYSTICK_WIRING_v26.10.01.01.md
- ARDUINO_IDE_SETTINGS_v26.10.01.01.md

After flashing, verify AI0 E-stop and AI1 joystick diagnostics, confirm physical
Left/Right polarity at low speed, prove a fresh boot enters System Un-Calibrated,
and perform the normal Limit Calibration or known Slip re-reference before motion.
