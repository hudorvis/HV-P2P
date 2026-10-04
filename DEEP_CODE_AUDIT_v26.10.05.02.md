# HV P2P v26.10.05.02 deep code audit

Date: 2026-10-05

## Scope

This hotfix audits the GitHub failure from `python -m tools.test_backend_logic` in `.05.01`, specifically the interaction between startup fail-safe state, persisted calibration/reference state, and canonical SRVR status priority.

## Failure

GitHub reached the backend runtime suite successfully, proving the import path was correct, then failed at the fresh-backend assertion:

`assert b2._not_calibrated and b2.bannerText == "System | Uncalibrated"`

## Root cause

`WinchState.estop_active` intentionally defaults to `True`. A normal running SRVR clears or retains that fail-safe state only after live CTRL/W1P safety evaluation. The test used `smoke_test=True`, which does not start the live network/control threads, then immediately asked the canonical status resolver for the banner.

The resolver correctly gives E-stop/fault precedence over service/unreferenced states. Therefore `_not_calibrated` was true, but the banner was correctly red rather than yellow while the synthetic initial safety latch remained set.

This was a regression-fixture error, not a production status bug.

## Correction

The runtime regression now isolates the behavior it is intended to prove:

1. construct the fresh backend;
2. assert `_not_calibrated` is true, proving the runtime reference was not persisted;
3. clear only `b2.state.estop_active` inside the test fixture;
4. assert `bannerText == "System | Uncalibrated"`.

Production startup remains fail-safe; no default safety value or status precedence was changed.

## Additional prevention

`test_backend_status_runtime_contract_0502.py` is now part of the normal source suite. It enforces that production still starts fail-safe, E-stop remains higher priority than Uncalibrated, and the PySide runtime test explicitly isolates the synthetic startup safety latch before checking the yellow banner.

## Verification

The complete final-layout source suite reports `ALL_SOURCE_CHECKS_PASS`, including 370 EdgeBox integration checks, 53 build-pipeline checks, release consistency, source hygiene, Python syntax, and SRVR preflight. PySide6 is unavailable in the local source-audit environment, so GitHub remains the authoritative execution of `tools.test_backend_logic`.
