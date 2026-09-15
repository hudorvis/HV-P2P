# HV P2P SRVR v26.09.15.01 — Qt Quick desktop build source

This SRVR source continues from the audited/hardened v26.08.31.08 control baseline. v26.09.15.01 locks the newly approved **Run** and **Setup** page revisions while retaining the existing Free-D, Log, communication, safety, calibration and configuration behavior unless explicitly noted below.

## v26.09.15.01 operator revisions

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

## SRVR-authoritative CTRL/W1P firmware

SRVR v26.09.15.01 carries one immutable firmware bundle built before any native desktop package. At application startup `firmware_authority.py` validates the exact bundle/release, CTRL/W1P role and EdgeBox target identities, image sizes, complete SHA-256 values and embedded binary tokens, then exposes read-only role-specific manifest/image endpoints on TCP 8088. SRVR fails closed if this packaged authority bundle is absent or invalid.

CTRL and W1P perform authority convergence only from their startup safety hold. Equal versions require exact running-image SHA-256, older/mismatched images use the validated inactive-partition OTA path, and a device newer than SRVR is never automatically downgraded. W1P additionally reuses its existing stopped/braked service gate before any authority flash write. CTRL must match SRVR before its established CTRL-TS RS485 updater is permitted to start.

See the repository-root `INITIAL_BOOTSTRAP_v26.09.15.01.md` for the one-time bootstrap and future release sequence.

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

The source-package preparation gates report:

- integrated EdgeBox/SRVR validation: **326 checks PASS**;
- automatic SRVR OTA contract: **38/38 PASS**;
- firmware authority HTTP test: PASS;
- immutable firmware bundle builder/validator test: PASS;
- build-pipeline validation: **54 checks PASS**;
- RS485 framing, CTRL-TS retry/target, Modbus, SRVR wire and Speed-mode contracts: PASS;
- Python syntax and static Qt/QML project preflight: PASS;
- full `tools/run_all_source_checks.py`: **ALL_SOURCE_CHECKS_PASS**.

The local preparation environment does not contain PySide6, `pyside6-deploy`, `pyside6-qmllint` or `arduino-cli`. GitHub Actions therefore remains authoritative for the pinned PySide6 backend/runtime tests, QML lint, native ESP32 compilation, and the three frozen desktop smoke tests.

## Build output

Use the repository-root workflow:

`.github/workflows/complete-build.yml`

It first builds CTRL-TS -> staged/final CTRL -> W1P and creates/verifies `SRVR_FIRMWARE_BUNDLE`. Both macOS native jobs and the Windows x64 job depend on that exact firmware artifact and package the same bundle. The Complete Release is created only after firmware, macOS Intel (`x86_64`), macOS Apple Silicon (`arm64`) and Windows x64 (`AMD64`) all pass.

A successful GitHub compile is not powered-motion commissioning approval. Complete the repository `NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.09.15.01.md` before hardware sign-off.

## Native desktop targets

The GitHub Complete Build freezes and smoke-tests this same source natively for:

- macOS Intel (`x86_64`);
- macOS Apple Silicon (`arm64`);
- Windows x64 (`AMD64`).

The app-private config directory is selected per operating system and Qt FileDialog URLs are normalized for Windows drive-letter and UNC paths.
