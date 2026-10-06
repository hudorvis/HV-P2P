# HV P2P v26.10.06.06 change summary

Date: 2026-10-06

Locked baseline: `v26.10.06.05`.

This is a CI/runtime-test fixture hotfix only. Production CTRL, W1P, CTRL-TS, SRVR backend, QML and firmware-authority behavior are unchanged from `.06.05` apart from release identity.

## GitHub failure

The macOS PySide runtime suite failed in `tools.test_backend_logic` at the assertion expecting `System | Active` immediately after clearing the synthetic Uncalibrated state.

`.06.05` intentionally added position/velocity-dependent yellow normal-motion states (`System | Near Limit`, `System | Far Limit`, and `System | Ramping`). The runtime test had retained position, ramp and signed-velocity state from earlier test sections. It therefore no longer had a deterministic stationary mid-span fixture when asserting `System | Active`.

## Fix

- Before the primary `System | Active` assertion, the runtime test now explicitly sets:
  - Near = 0.0 m;
  - Far = 100.0 m;
  - Current Position = 50.0 m;
  - measured speed = 0.0 m/s;
  - last signed VEL = 0.0 m/s.
- The assertion remains strict: status level 0, `systemReady == True`, and exactly `System | Active`.
- Added `tools/test_backend_status_fixture_contract_0606.py` to the normal source suite. It statically verifies that this clean stationary mid-span setup remains immediately before the PySide runtime assertion, so the same CI-only fixture leak is caught even where PySide6 is not installed.

## Locked behavior preserved

All `.06.05` runtime behavior remains unchanged, including:

- two-fresh-tap Confirm/Confirm? calibration behavior;
- rapid two-tap AUX handling;
- `System | Ramping`, `System | Near Limit`, and `System | Far Limit`;
- `.06.04` automatic-update recovery;
- W1P independent 500 ms VEL watchdog;
- normal ~150 ms SRVR non-zero VEL cadence;
- AI0 E-stop / AI1 joystick mapping;
- predictive/dynamic soft limits and hard-limit protection;
- Leadshine velocity/Modbus architecture;
- transactional calibration and Cancel behavior;
- `.06.02` progress smoothing, System-tab geometry, AUX ordering and short labels.

## Verification

The full source/static/regression/preflight suite passes through all historical updater/RS485/calibration/motion tests, 370 EdgeBox integration checks, the `.06.05` regression, the new `.06.06` fixture guard, 53 build-pipeline checks, release consistency, source hygiene, Python syntax and SRVR preflight.

PySide6 is not installed in the source-audit environment, so the exact `tools.test_backend_logic` runtime execution remains a GitHub desktop CI gate. Native ESP32 and frozen desktop compilation also remain GitHub Actions authoritative. No local firmware binaries are fabricated.
