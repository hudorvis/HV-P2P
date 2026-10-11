# HV P2P v26.10.11.01 change summary

Date: 2026-10-11

Source baseline: **v26.10.08.05**. W1P/CTRL/CTRL-TS firmware behaviour, the 115200/8N1 EL7 link, AI0/5 V W1P E-stop, EdgeBox DO0 brake control, CTRL-TS marker smoothing, updater, motion, calibration, AUX, limits and approved UI layout remain locked.

## GitHub failure confirmed

The user-supplied `.08.05` GitHub log proves the source/package/sign stages completed and the failure occurred only when CI launched the completed frozen macOS Intel executable with `--smoke-test`. That process exited with native `SIGSEGV`/139.

The same log also shows `pyside6-deploy` downloading and installing **Nuitka 4.3** at build time. The project had therefore lost compiler reproducibility: an otherwise unchanged source package could produce different native code depending on the newest Nuitka release available that day.

## Change 1 — deterministic desktop compiler line

The release now pins:

- Python **3.12.10** in all GitHub setup-python jobs;
- PySide6 **6.11.1**;
- Nuitka **4.2.2**.

The generated `pysidedeploy.spec` is patched to retain `nuitka==4.2.2`. CI verifies the installed Nuitka version after dependency installation, after deployment dry-run, immediately before freeze and after freeze on both macOS and Windows.

This does not alter SRVR application behaviour; it makes the native build reproducible and prevents `pyside6-deploy` from silently switching compilers.

## Change 2 — frozen SRVR call-path hardening

The `.08.04` Apple crash report pointed into Nuitka's generated call helper while `_build_controller_display_packet()` was active. `.08.05` reduced the new RS485 diagnostic/log path but GitHub still reproduced a frozen SIGSEGV.

For `.11.01`, nested functions and runtime lambdas have been removed from `backend.py`, including:

- DSP1/calibration formatting helpers;
- CTRL-TS telemetry integer parsers;
- config-migration helpers;
- calibration property-format helpers;
- geometry sort lambda.

Equivalent module/class-scoped or inline logic is used instead. This is deliberately a compiler-stability refactor only: packet contents, rates, safety authority and control algorithms are unchanged.

## Change 3 — better native crash gate and evidence

The frozen smoke test now:

1. runs the W1P RS485 diagnostic reducer;
2. builds/validates DSP1 **200 consecutive times**;
3. reports progress with `SMOKE PHASE:` markers;
4. enables Python `faulthandler` in smoke mode only;
5. emits deferred diagnostics and processes Qt events.

On macOS, CI captures the smoke output and, if the frozen app exits abnormally, prints recent Apple `DiagnosticReports` crash data before failing the job. The same diagnostics are now applied again to the signed app after release-ZIP round trip.

Smoke-test persistence is also isolated in a private temporary directory. Source/frozen smoke tests can no longer read, alter or inherit the operator's real `Application Support/HV P2P SRVR/config.json`, so repeated CI runs are deterministic and manual smoke testing cannot overwrite live configuration.

## Locked production behaviour

- W1P operational EL7 Modbus: **115200 baud / 8N1 / slave ID 1** (`P05.29=4`, `P05.30=6`, `P05.31=1`).
- 38400/8N2 remains a stopped/read-only diagnostic probe only.
- W1P local E-stop remains **AI0 / 5 V**, fail-closed.
- EdgeBox **DO0 / GPIO40** remains the physical brake-coil switch; LOW/off applies the brake and verified EL7 logical `BRK-OFF` remains sequencing authority.
- CTRL → W1P → CTRL-TS firmware order/status remains unchanged.
- Motion, limits, calibration, AUX, watchdogs, firmware authority, Free-D and UI behaviour remain unchanged.

## Validation

Local source validation passed the complete constituent regression set: **386 EdgeBox integration checks**, **58 build-pipeline checks**, updater/OTA, Modbus/wire/motion contracts, release consistency, source hygiene, Python syntax, SRVR preflight and the new frozen-runtime/build-toolchain guards. The combined runner reached the environment execution limit at the final motion-contract stage; that test and every remaining constituent check were rerun separately and passed.

Native Arduino compilation and the actual frozen macOS/Windows runtime remain GitHub Actions gates; this environment cannot execute a macOS Nuitka binary.
