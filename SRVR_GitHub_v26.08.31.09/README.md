# HV P2P SRVR v26.08.31.09 — Qt Quick macOS Intel build source

This SRVR source continues from the audited/hardened v26.08.31.08 control baseline. v26.08.31.09 locks the newly approved **Run** and **Setup** page revisions while retaining the existing Free-D, Log, communication, safety, calibration and configuration behavior unless explicitly noted below.

## v26.08.31.09 operator revisions

### Run

- Top-left logo is `HV P2P` / `SRVR`; the separate `HV P2P | SRVR` heading is removed.
- Run Shortcut `Save`, `Recall` and `Slip` actions use one global five-second two-stage confirmation. The first press changes that same button to `Confirm? 5s`; a second press executes the original action. Timeout, switching Shortcuts tabs, leaving the page, or selecting another immediate/pending Shortcut action cancels the prior confirmation.
- Preset names/positions/visibility and System mode controls retain their established semantics.
- System `Mode 1` and `Mode 2` are fully readable and the first action controls share one left alignment.
- `TO NEAR` / `TO FAR` metre units are placed beside their values.

### Setup

- CTRL and W1P panels have matching six-row status geometry and aligned dividers.
- CTRL rows: `CTRL IP`, `Link`, `RS485`, `E-Stop`, `Firmware`, `Direction`.
- W1P rows: `W1P IP`, `Link`, `RS485`, `E-Stop`, `Firmware`, `Direction`.
- The actual CTRL and W1P firmware versions are reported over their existing status protocols and exposed to QML.
- Motion Profiles preserves the existing data/controls with even clearance around the Mode 1/Mode 2 centre divider.
- The former `CTRL-TS / FIRMWARE` panel is now `CTRL-TS`, containing `CTRL-TS Link`, a divider, `Detected`, `Required`, and `Update`. Link uses the same green Active/red Disconnected model as the CTRL/W1P Link rows.

## Virtual Position Source

Setup `Position Source` offers `Encoder` and `Virtual`.

`Virtual` is an SRVR-local demo source intended for exercising real CTRL/CTRL-TS input without producing physical winch motion. While Virtual is active:

- the normal SRVR motion/profile/limit logic calculates a simulated position and speed;
- `_send_velocity()` never emits a non-zero W1P `VEL` packet;
- any connected W1P is positively held with periodic `STOP` and `SW_SRVON 0` commands;
- W1P/EL7 link health is not required for the demo simulation, but CTRL/SRVR input and safety health remain authoritative;
- physical W1P `POS_M`/`VEL_MPS` telemetry cannot overwrite the simulation;
- Slip/re-reference does not send physical `SYNC_POS`.

Changing back to `Encoder` stops the simulation, keeps physical Servo Enable inhibited, and requires the existing joystick-neutral/re-arm sequence before physical motion can resume.

## Inherited safety / build behavior

The release retains the v26.08.31.07/.08 protections, including:

- independent 650 ms W1P VEL-command deadman;
- fail-closed W1P OTA/reboot/NVS service-safe gate;
- CTRL/W1P OTA content-role verification;
- transactional W1P IP readdress with lost-ACK proof and automatic rollback;
- atomic/recoverable private SRVR configuration;
- Free-D full-range `u24` lens output and incoming checksum validation;
- pinned Waveshare dependency commit and GitHub native-build manifest;
- stable/versioned macOS bundle metadata;
- original nested SRVR ZIP preservation and release SHA-256 manifests.

## Interface and protocol contract

The core on-wire/control behavior remains compatible:

- CTRL A6/A7 joystick/status transport on UDP/5000 and five CTRL AUX flags;
- CTRL-TS HMI status/version/hash/update path;
- W1P command set including `SET_UNITS_PER_M`, `SET_MOTOR_REVERSE`, `SET_ACCEL`, `SET_DECEL`, `SET_CROSSOVER`, `SET_STOP_DECEL`, `SET_ACCEL_MODE`, `SET_SPAN`, `SET_LIMIT_NEAR`, `SET_LIMIT_FAR`, `SERVICE_MODE`, `VEL`, `SYNC_POS`, `STOP` and `SW_SRVON`;
- W1P/EL7 RS485 diagnostics, software Servo Enable, E-stop, brake/output-map checks and watchdog/service safety reporting;
- staged Setup and Free-D Apply/Reset semantics and transferable configuration files;
- joystick Left/Centre/Right calibration and neutral-return interlocks.

## Validation

The source-package preparation gates currently report:

- integrated EdgeBox/SRVR validation: **316 checks PASS**;
- build-pipeline validation: **34 checks PASS**;
- RS485 host framing/CRC: PASS;
- CTRL-TS updater retry/target gating: PASS;
- Modbus host contract: PASS;
- SRVR A7 wire contract: PASS;
- Python syntax and static Qt/QML project preflight: PASS;
- full `tools/run_all_source_checks.py`: **ALL_SOURCE_CHECKS_PASS**.

The local preparation environment does not contain PySide6 or the native ESP32 Arduino toolchain. The GitHub macOS job therefore remains authoritative for the PySide6 runtime/backend regression (which includes Virtual-mode runtime assertions), `pyside6-qmllint`, app smoke tests and native firmware compilation.

## Build output

Use the repository-root workflow:

`.github/workflows/complete-build.yml`

It builds the matched v26.08.31.09 CTRL-TS, CTRL and W1P firmware, freezes/smoke-tests the Intel (`x86_64`) macOS SRVR application, preserves the original SRVR distribution ZIP, and publishes the complete matched release.

A successful GitHub compile is not powered-motion commissioning approval. Complete the repository `NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.08.31.09.md` before hardware sign-off.
