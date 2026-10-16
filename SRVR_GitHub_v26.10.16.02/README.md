# HV P2P SRVR v26.10.16.02 — Qt Quick desktop build source

This SRVR source is locked to `v26.10.08.04` except for the macOS frozen-runtime hardening described below. Approved Run/Setup layout, motion, calibration, AUX, firmware authority, 115200/8N1 Leadshine communications, AI0 W1P E-stop and DO0 brake behavior remain unchanged.

## v26.10.16.02 macOS frozen-runtime crash fix

The `.08.04` macOS Intel crash report showed a native `EXC_BAD_ACCESS` in Nuitka's generated call helper while `_tick` was building the CTRL DSP1 display packet. The DSP1 builder is source-identical to `.08.03`; the new `.08.04` RS485 diagnostic path ran immediately before it. `.08.05` keeps the same `[W1P RS485]` messages but makes diagnostic reduction plain-data only and defers the Qt log signal until after DSP1 construction.

The packaged-app smoke test now executes the exact RS485-diagnostic -> repeated-DSP1 sequence inside the frozen macOS Intel and Apple Silicon binaries, so this native path is exercised before release publication.

## Leadshine RS485 diagnostics retained from v26.10.08.04

W1P normal Leadshine communication remains **115200 baud / 8N1 / Modbus ID 1** (`P05.29=4`, `P05.30=6`, `P05.31=1`). The EL7 factory **38400/8N2** format remains only a stopped, read-only diagnostic probe.

SRVR converts W1P's existing RS485/configuration/feedback STATUS evidence into transition-based `[W1P RS485]` log entries. No-response, alternate-format detection, configuration-read faults, parameter mismatch, feedback/SRDY faults and verified recovery remain visible on the Log page and in saved log files without flooding the log at the W1P status rate.

## v26.10.16.02 automatic-update recovery

This revision keeps the `.06.02` operator/motion/UI changes locked and changes only SRVR firmware coordination/recovery. The normal background `SRVR_FW` node-pull path remains first choice, but the verified HTTP fallback is now evaluated by the background communications worker as well as the Qt path, so a stale CTRL/W1P no longer needs a manual reboot merely because the primary pull was missed.

CTRL remains the mandatory first stage and W1P is attempted second. A present W1P that is actively flashing receives a long completion window; a W1P that cannot converge (for example `update_waiting_safe_idle`) receives a bounded ordered recovery window and remains fail-closed, while the independent CTRL-TS final stage is eventually released instead of remaining at `Waiting` forever. The CTRL-TS safe RS485 flash/reboot protocol itself is unchanged.

## v26.10.16.02 operator revisions

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
- CTRL and W1P `Firmware` readouts normally show the running ESP32 version and temporarily show the live update phase/percentage while that node is updating.
- Motion Profiles preserves the existing data/controls with even clearance around the Mode 1/Mode 2 centre divider.
- The `CTRL-TS` panel now matches CTRL/W1P firmware presentation: `Link`, a divider, and one `Firmware` readout that normally shows the detected running version and switches to update progress during CTRL-TS firmware activity.


### v26.10.16.02 transport/display integration

- CTRL now reports its own authority-OTA progress back to SRVR over the existing UDP control link as well as to CTRL-TS; W1P continues to report `FW_PROGRESS` directly to SRVR.
- CTRL/W1P/CTRL-TS Settings firmware fields therefore use one version-or-progress model.
- Battery Change/Acceleration Settings selectors follow live state changes made from CTRL-TS AUX controls instead of a stale Setup draft mirror.
- Battery Change/service-mode `TO NEAR` / `TO FAR` values remain signed outside the calibrated limits.
- CTRL-TS self-update remains deliberately last after CTRL/W1P progress completes. Its own flash write remains headless/display-off while SRVR shows the exact percentage.
- The approved panel geometry is retained; only the CTRL-TS firmware rows are consolidated as requested.

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

- independent 500 ms W1P VEL-command deadman;
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
- auto-saved Settings and Free-D edits plus transferable configuration files;
- joystick Left/Centre/Right calibration and neutral-return interlocks.

## Validation

The source-package preparation gates currently report:

- integrated EdgeBox/SRVR validation: **370 checks PASS**;
- build-pipeline validation: **53 checks PASS**;
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

It builds the matched v26.10.16.02 CTRL-TS, CTRL and W1P firmware, freezes/smoke-tests the Intel (`x86_64`) macOS SRVR application, preserves the original SRVR distribution ZIP, and publishes the complete matched release.

A successful GitHub compile is not powered-motion commissioning approval. Complete the repository `NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.10.16.02.md` before hardware sign-off.


## Native desktop targets

The GitHub Complete Build freezes and smoke-tests this same source natively for:

- macOS Intel (`x86_64`);
- macOS Apple Silicon (`arm64`);
- Windows x64 (`AMD64`).

The app-private config directory is selected per operating system and Qt FileDialog URLs are normalized for Windows drive-letter and UNC paths.
