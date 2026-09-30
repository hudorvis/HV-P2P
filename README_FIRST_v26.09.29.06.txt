HV P2P v26.09.29.06 - GITHUB READY SOURCE

PURPOSE
This is the functional successor to v26.09.29.05. It retains the audited
v26.09.29.x RS485/OTA/Leadshine/EdgeBox safety baseline and adds the requested
preset-name consistency, joystick centre-drift management and predictive stopping.

IMPORTANT
GitHub Actions is the authoritative native compiler. This source package does
NOT contain fabricated ESP32 application binaries, Windows executables or macOS
applications. The workflow builds CTRL-TS first, embeds that exact native image
and SHA into staged CTRL, then builds CTRL and W1P before creating the matching
SRVR desktop artifacts and Complete Release.

KEY v26.09.29.06 CHANGES
- CTRL Setup now shows Value / Percentage with an exactly aligned right column.
- Run -> Shortcuts -> System adds Preset Names: Short Names / Long Names.
- The selected preset-name style is used consistently by SRVR Top/Side views and
  CTRL-TS while long names remain editable and P1..P10 remain fixed identifiers.
- Adds bounded, runtime-only automatic joystick-centre drift compensation under
  strict stationary/neutral qualification; saved calibration is never silently
  rewritten.
- Adds reaction-aware predictive stopping in SRVR and independent local W1P
  dynamic soft-limit enforcement while preserving hard limits.
- Rechecks Speed/Dynamic mode for incline use: the Leadshine remains in
  closed-loop velocity mode, W1P uses bounded measured-speed PI correction, and
  downhill braking is expected as regenerative/negative servo torque without
  reversing the requested travel direction.
- Retains AI0/pin14 E-stop, AI1/pin16 joystick, 8-sample trimmed joystick
  filtering, 500 ms W1P VEL watchdog and 150 ms SRVR VEL refresh.
- Adds dedicated regression tests for the new motion/UI contracts.

FIRST COMMISSIONING
Use the GitHub-produced COMPLETE_RELEASE/FIRMWARE/STAGED_SOURCE folders for any
manual commissioning flash. Read:
- INITIAL_BOOTSTRAP_v26.09.29.06.md
- NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.09.29.06.md
- CTRL_JOYSTICK_WIRING_v26.09.29.06.md
- ARDUINO_IDE_SETTINGS_v26.09.29.06.md

Commission predictive limits and incline Speed mode from low speed/light load
upward. Regenerative braking energy is a physical drive/resistor constraint and
must be verified on the real installation.
