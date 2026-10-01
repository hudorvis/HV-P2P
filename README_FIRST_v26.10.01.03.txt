HV P2P v26.10.01.03 - GITHUB READY SOURCE

PURPOSE
This is the direct successor to v26.10.01.02. It keeps the approved HV P2P
motion/safety architecture while fixing joystick calibration readout and CTRL
telemetry latency, and implements the requested Settings/Free-D auto-save model.

IMPORTANT
GitHub Actions is the authoritative native compiler. This source package does
NOT contain fabricated ESP32 application binaries, Windows executables or macOS
applications. The workflow builds CTRL-TS first, embeds that exact native image
and SHA into staged CTRL, then builds CTRL and W1P before creating matching SRVR
desktop artifacts and the Complete Release.

KEY v26.10.01.03 CHANGES
- Joystick calibration becomes active and saved as soon as the three-step wizard
  completes; Setup Value/Percentage immediately use the calibrated range.
- Removed the Settings and Free-D Apply/Reset footer controls. Accepted changes
  auto-save; editable text fields commit on Enter/focus loss rather than each key.
- Removed v26.10.01.02's blocking two-second HTTP authority poll from healthy CTRL
  and W1P loops. SRVR now sends lightweight UDP release beacons; HTTP/SHA/OTA is
  entered only after a node has already detected a release mismatch and gone
  fail-closed.
- Normal CTRL AI1 acquisition/A7 telemetry can therefore continue at its intended
  20 Hz without periodic manifest-request stalls.
- W1P's independent 500 ms velocity freshness watchdog and all Servo Enable,
  E-stop, hard-limit and predictive-stop protections are retained.
- v26.10.01.02's automatic release convergence, CTRL-TS stable update screen and
  E-stop source formatting fixes remain in place.
- v26.10.01.01's AI0/AI1 transaction hardening, session-only position reference,
  red/yellow/green status priority and corrected physical joystick polarity remain.

VERSION / BUILD IDENTITY
Application/release: 26.10.01.03
macOS short version: 26.10.1
macOS bundle build: 2610.1.3

FIRST COMMISSIONING
Use the GitHub-produced COMPLETE_RELEASE/FIRMWARE/STAGED_SOURCE folders for any
manual commissioning flash. Read:
- INITIAL_BOOTSTRAP_v26.10.01.03.md
- NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.10.01.03.md
- CTRL_JOYSTICK_WIRING_v26.10.01.03.md
- ARDUINO_IDE_SETTINGS_v26.10.01.03.md

After flashing, verify joystick Value/Percentage responds without visible periodic
stalls, perform Left/Centre/Right calibration and confirm approximately
-100/0/+100%, verify auto-save by leaving/re-entering Settings and Free-D, and
complete the normal Limit Calibration or known Slip re-reference before motion.
