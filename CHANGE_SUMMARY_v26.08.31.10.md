# HV P2P v26.08.31.10 Change Summary

v26.08.31.10 is the corrected GitHub-build revision following the issued v26.08.31.09 source pack. It retains the complete v26.08.31.09 Run/Setup revision and all inherited v26.08.31.07/.08 safety/build fixes unchanged, while correcting the two SRVR Virtual-mode CI issues exposed by the first .09 GitHub run.

## v26.08.31.09 functionality retained unchanged

### Locked SRVR Run revision

- Top-left logo is two lines: `HV P2P` / `SRVR`; the separate `HV P2P | SRVR` heading is removed.
- Every Run-page Shortcut `Save`, `Recall` and `Slip` action uses the locked two-step five-second confirmation behavior.
- Shortcuts/System retains the existing direct control semantics for `Power/Speed`, `Off/On`, `Mode 1/Mode 2`, editable drive-mode names and calibration actions.
- `Mode 1` / `Mode 2` remain fully visible and System controls retain the approved common alignment.
- Position `TO NEAR` / `TO FAR` metre units remain adjacent to their values.

### Locked SRVR Setup revision

- CTRL rows: `CTRL IP`, `Link`, `RS485`, `E-Stop`, `Firmware`, `Direction`.
- W1P rows: `W1P IP`, `Link`, `RS485`, `E-Stop`, `Firmware`, `Direction`.
- CTRL/W1P panels retain identical six-row geometry and divider position.
- CTRL/W1P firmware versions are reported from the actual controllers.
- Motion Profiles retains equal Mode 1 / Mode 2 divider clearance.
- `CTRL-TS` contains `CTRL-TS Link`, divider, `Detected`, `Required`, `Update`, with green `Active` / red `Disconnected` link status.
- `Position Source` remains `Encoder` / `Virtual`.

### Virtual Position Source behavior retained

While Virtual is active:

- SRVR simulates position and speed locally from the normal motion/profile/limit logic.
- SRVR never emits a non-zero W1P `VEL` command.
- Any physical W1P is positively held using `STOP` and `SW_SRVON 0` when real I/O is enabled.
- Software Servo Enable remains inhibited.
- Physical W1P position/speed telemetry cannot overwrite the virtual state.
- Virtual Slip/re-reference does not send physical `SYNC_POS`.
- Returning to Encoder requires the normal safe neutral/re-arm path before physical motion can resume.

## v26.08.31.10 CI corrections

The first issued v26.08.31.09 source pack reached the macOS backend runtime regression and exposed two issues before a compiled .09 release was produced:

1. Entering Virtual previously latched `_safety_servo_inhibited` only through the helper that also sends hardware output. CI/smoke-test mode intentionally suppresses physical I/O, so the local inhibit state did not become true. v26.08.31.10 makes the local Servo Enable inhibit an unconditional part of the Virtual mode transition; real `STOP` / `SW_SRVON 0` transmission remains conditional on real hardware I/O.
2. The next Virtual motion assertion inherited reversed joystick/calibration state from earlier test cases in the same backend instance. The regression now establishes an explicit neutral demo-test state before validating simulated positive motion.

These corrections do **not** redesign the locked Run or Setup QML, change firmware communication protocols, change physical W1P motion behavior, or alter Free-D, Log or CTRL-TS operator layouts.

## Build/release status

- Integrated source validation: 316 checks PASS.
- Build-pipeline validation: 34 checks PASS.
- Full `tools/run_all_source_checks.py`: PASS.
- RS485 framing, HMI updater retry/target gates, Modbus host contract, SRVR wire contract, Python syntax and SRVR static/QML preflight: PASS.
- Native ESP32 compilation and the real PySide6 macOS backend regression remain mandatory GitHub Actions gates.
- No v26.08.31.10 compiled binaries are included in this source pack.
