# HV P2P v26.08.31.09 Change Summary

v26.08.31.09 continues directly from the fully hardened v26.08.31.08 source baseline. All v26.08.31.07/.08 safety, OTA, persistence, Free-D and reproducible-build fixes are retained. This release locks the newly approved SRVR Run and Setup revisions and adds the requested Virtual demo position source.

## Locked SRVR Run revision

- Top-left logo is now two lines: `HV P2P` / `SRVR`; the separate `HV P2P | SRVR` heading is removed.
- Every Run-page Shortcut `Save`, `Recall` and `Slip` action is now a two-step confirmation. First press changes that same button to `Confirm? 5s`; a second press within five seconds performs the original action. Timeout restores the normal button. Selecting another Shortcut action cancels the previous pending confirmation and starts the new one. Immediate controls such as mode buttons and visibility toggles cancel any pending confirmation and remain immediate.
- Shortcuts/System retains the existing control semantics. `Power/Speed`, `Off/On`, `Mode 1/Mode 2`, editable drive-mode names, and calibration buttons are not converted to Save/Recall controls.
- `Mode 1` and `Mode 2` are wide enough to display fully. The System action area uses one common label column so Power, Off, Mode 1 and Limit Calibration begin at the same horizontal position.
- Position `TO NEAR` / `TO FAR` units are kept immediately beside their values.

## Locked SRVR Setup revision

- CTRL and W1P panels retain their existing allocation and now use matching six-row diagnostic geometry with the divider at the same vertical position.
- CTRL rows: `CTRL IP`, `Link`, `RS485`, `E-Stop`, `Firmware`, `Direction`.
- W1P rows: `W1P IP`, `Link`, `RS485`, `E-Stop`, `Firmware`, `Direction`.
- CTRL `RS485` reports CTRL↔CTRL-TS link state. W1P `RS485` reports W1P↔EL7 link state.
- CTRL and W1P publish their actual firmware version into the existing status protocols so Setup can show a real `Firmware` value rather than a hard-coded display value.
- Motion Profiles keeps the same data and panel geometry, but Mode 1/Mode 2 receive equal clearance from the centre divider.
- `CTRL-TS / FIRMWARE` is renamed `CTRL-TS`. It contains `CTRL-TS Link`, divider, `Detected`, `Required`, and `Update`. CTRL-TS Link uses the same green `Active` / red `Disconnected` status model as CTRL/W1P Link.

## Virtual Position Source demo mode

Setup `Position Source` now offers `Encoder` and `Virtual`. `Virtual` is deliberately an SRVR-local demonstration mode for exercising the real CTRL/CTRL-TS joystick and shortcut workflow without driving the physical winch.

While Virtual is active:

- SRVR simulates position and speed locally from the same motion/profile/limit logic.
- SRVR never emits a non-zero W1P `VEL` command.
- SRVR periodically sends `STOP` and `SW_SRVON 0` to any physical W1P that is present and keeps its software Servo Enable inhibited.
- W1P/EL7 link health is not required for the demo simulation, while SRVR/CTRL/CTRL-TS safety/input health remains authoritative.
- Physical W1P position/speed telemetry cannot overwrite the virtual position.
- Slip/re-reference actions update only the virtual SRVR position and do not send physical `SYNC_POS`.

Returning from Virtual to Encoder stops the simulation, keeps physical Servo Enable inhibited, and requires the normal joystick-neutral/re-arm sequence before physical motion can resume.

## Build/release status

- Integrated source validation: 316 checks PASS.
- Build-pipeline validation: 34 checks PASS.
- Full `tools/run_all_source_checks.py`: PASS.
- RS485 framing, HMI updater retry/target gates, Modbus host contract, SRVR A7 wire contract, Python syntax and SRVR static/QML preflight: PASS.
- The PySide6 runtime backend regression (including Virtual-mode runtime assertions) remains a mandatory GitHub macOS CI step. PySide6 is not installed in the source-pack preparation container, so no local runtime-pass claim is made.
- Native ESP32 firmware compilation remains the GitHub Actions gate; this source release contains no fabricated .09 binaries.
