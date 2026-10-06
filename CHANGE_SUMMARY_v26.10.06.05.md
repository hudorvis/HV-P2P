# HV P2P v26.10.06.05 change summary

Date: 2026-10-06

Locked baseline: `v26.10.06.04`. This revision changes only the three requested areas: CTRL-TS calibration confirmation handling, rapid two-tap AUX confirmation, and new normal-motion System status states. All `.06.04` firmware-update recovery behavior and prior motion/UI fixes remain locked.

## 1. Calibration wizard Confirm -> Confirm? consistency

### Root cause
CTRL AUX1..AUX5 are touchscreen-only in the current EdgeBox architecture. After CTRL-TS sent a confirmed AUX event, CTRL represented that event for roughly 300 ms in its A7 AUX flag bits. CTRL-TS also consumed those returned bits through `apply_flags_to_aux()` as though they were a new operator press.

If the reflected AUX pulse arrived after the old 400 ms local suppression window and after the wizard had advanced, it could silently become the first press of the next calibration step. The next real touchscreen tap then appeared to complete the action in one press. The exact result depended on RS485/status timing, which explains the intermittent bench behavior.

### Fix
- Returned CTRL AUX flags are now diagnostic/transport state only; they cannot enter the local CTRL-TS select/confirm state machine.
- Every Joystick, Limit and Winch calibration kind/step transition clears both `selected_aux` and `confirmed_aux` state.
- Each calibration step therefore starts at Ready and requires two fresh local touchscreen click events.

## 2. Rapid two-tap AUX confirmation

### Root cause
The old code required at least 250 ms between the first and second tap, and measured that interval when the main loop processed the queue. Two legitimate quick taps could already be queued together, be processed in the same loop iteration, and cause the second tap to be discarded.

### Fix
- Removed the 250 ms select-to-confirm processing delay.
- LVGL `CLICKED` is treated as one completed operator press.
- Added only a 35 ms duplicate-callback debounce at event capture.
- Two deliberate taps can now be queued and processed back-to-back; first selects (`Confirm?`), second executes (`Confirmed`).
- Removed the obsolete 400 ms AUX echo-suppression timer because reflected CTRL flags can no longer act as local presses.

## 3. New yellow System states

The canonical SRVR status resolver now adds:

- `System | Near Limit` within 1.0 m of the calibrated Near endpoint;
- `System | Far Limit` within 1.0 m of the calibrated Far endpoint;
- `System | Ramping` while the system is actually moving toward Near/Far inside that endpoint's configured ramp zone.

Priority remains unchanged and safety-first: red E-stop/fault, calibration/service/Battery Change/Uncalibrated yellow, then endpoint/ramping yellow, otherwise `System | Active` green. These states are presentation-only and do not alter velocity, limits, ramps or stopping calculations. Because SRVR is the single status authority, SRVR and CTRL-TS receive identical wording and level.

## Locked behavior preserved

- `.06.04` automatic CTRL -> W1P -> CTRL-TS update recovery and RS485 diagnostics;
- CTRL↔CTRL-TS single-flight EVENT ACK/retry;
- W1P independent 500 ms VEL watchdog;
- normal ~150 ms SRVR non-zero VEL cadence;
- AI0 E-stop / AI1 joystick mapping;
- predictive/dynamic soft limits and hard-limit protection;
- Leadshine Modbus/velocity architecture;
- transactional calibration and Cancel behavior;
- `.06.02` progress smoothing, System-tab geometry, AUX ordering and short labels.

## Verification

All historical source/static/regression/preflight checks pass after the change, including 370 EdgeBox integration checks, the `.06.04` updater/RS485 regression, the new `test_bench_regression_0605.py`, 53 build-pipeline checks, release consistency, source hygiene, Python syntax and SRVR preflight. Native ESP32 and frozen desktop/PySide compilation remain GitHub Actions gates; no local firmware binaries are fabricated.
