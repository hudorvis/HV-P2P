# HV P2P v26.10.05.02 change summary

Date: 2026-10-05

Authoritative lineage: `HV P2P v26.10.05.01 - GitHub Ready Source.zip` -> this CI runtime-contract hotfix.

## Corrected GitHub PySide runtime regression

The `.05.01` GitHub desktop job imported the application backend successfully, then failed in `tools.test_backend_logic` while checking that a fresh backend remains `System | Uncalibrated` after a runtime Ref slip is deliberately not persisted.

The production backend was already correct. `WinchState.estop_active` intentionally starts `True` until live CTRL/W1P safety state is evaluated. The regression created a fresh `smoke_test=True` backend and immediately asserted the yellow banner without first removing that synthetic startup safety latch. Because E-stop/fault has higher status priority than Uncalibrated, the assertion mixed two independent conditions.

`.05.02` fixes the test fixture rather than weakening production safety:

- assert `_not_calibrated` remains true on the fresh backend;
- clear only the synthetic `b2.state.estop_active` test latch;
- then assert the canonical yellow `System | Uncalibrated` banner.

A new `test_backend_status_runtime_contract_0502.py` is included in `run_all_source_checks.py`, so this exact fixture/status-priority mismatch is detected in source-audit environments where PySide6 is not installed.

## Preserved `.05.01` behavior

No CTRL/W1P/CTRL-TS transport timing, updater sequencing, HMI motion/status packet behavior, QML layout, Battery Change behavior, calibration workflow, Leadshine control, hard-limit logic, predictive stopping, or W1P 500 ms velocity watchdog was changed by this hotfix.

## Verification

The final `.05.02` source tree passes the complete source/static/preflight suite, including 370 EdgeBox integration checks, the new backend-status source contract, RS485/update/AUX contracts, 53 build-pipeline checks, release consistency, source hygiene, Python syntax, and SRVR preflight. GitHub Actions remains authoritative for the PySide6 runtime execution and native firmware/desktop builds.
