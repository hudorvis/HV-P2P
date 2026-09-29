HV P2P v26.09.29.02 - GITHUB READY SOURCE

PURPOSE
This release is the audited successor to the user-supplied authoritative
HV P2P v26.09.27.01 source. It incorporates the defects found during the
v26.09.27.01 deep code audit and the subsequent real-hardware CTRL/CTRL-TS
commissioning tests on 29 September 2026.

IMPORTANT
GitHub Actions is the authoritative native compiler. This source package does
NOT contain fabricated ESP32 application binaries, Windows executables or macOS
applications. The included workflow builds CTRL-TS first, embeds that exact
native image and SHA into staged CTRL, then builds CTRL and W1P before creating
the matching SRVR desktop artifacts and Complete Release.

KEY v26.09.29.02 CHANGES
- fixes the SRVR/W1P STATUS field mismatch that rejected real W1P STATUS packets;
- prevents PR0 from triggering a stale velocity after a failed velocity write;
- correctly decodes Modbus write exception replies and preserves two-failure
  link-health hysteresis;
- makes W1P safety stop a bounded best-effort attempt even after link health drops;
- requires a new CTRL/CTRL-TS HELLO/COMPATIBLE session after every TS reboot;
- correlates normal CTRL-TS EVENT replies to the outstanding POLL sequence;
- clears stale CTRL-TS identity after HMI link loss;
- adds stable CTRL-TS OTA splash ownership and a real graphical progress bar;
- adds CTRL-TS PSRAM/display diagnostics plus headless RS485 recovery mode;
- corrects the locked Run UI vertical fit from ~429 px to 472 px on the 480 px
  panel without changing the approved horizontal layout/content;
- uses the EdgeBox-supported 16M partition-menu option while sketch-local partitions.csv supplies the actual dual-OTA layout;
- adds regression checks for the audit defects above.

FIRST COMMISSIONING
Use the GitHub-produced COMPLETE_RELEASE/FIRMWARE/STAGED_SOURCE folders for any
manual commissioning flash. See INITIAL_BOOTSTRAP_v26.09.29.02.md and
NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.09.29.02.md before bench testing.

CTRL joystick wiring and exact Arduino IDE settings are documented in:
- CTRL_JOYSTICK_WIRING_v26.09.29.02.md
- ARDUINO_IDE_SETTINGS_v26.09.29.02.md
