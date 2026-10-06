# HV P2P v26.10.06.08 deep code audit

Date: 2026-10-06
Baseline: `v26.10.06.07`

## Scope lock

The baseline was treated as locked. Functional production edits are restricted to:

1. CTRL-TS travel-marker display interpolation.
2. SRVR canonical `System | Ramping` presentation semantics.

W1P/Leadshine was audited end-to-end but its production logic was not changed. A normalized `.06.07 -> .06.08` production diff confirms CTRL, W1P, firmware authority and Run/Settings QML are unchanged apart from release identity.

## Finding A — marker back-step was caused by prediction, not an inaccurate encoder source

HMM1 motion telemetry is intentionally rate-limited to roughly 10 Hz. `.06.07` attempted to make that look fluid by projecting the last verified `pos_frac` forward from signed measured speed. At higher speed this could display a point ahead of the following real sample. The next verified sample then corrected the display backwards.

The `.06.08` renderer is intentionally lagged by roughly one HMM1 sample interval instead of predicting ahead. Each new verified position defines the end of a local interpolation segment. The marker is serviced every 16 ms and linearly traverses that segment using a lightly filtered/clamped observed sample interval. Direction-aware jitter suppression prevents count-level opposite-direction display twitch while clearly moving. The display can settle exactly when stopped.

This is display-only. `g_pos`, authoritative `g_pos_frac`, SRVR/W1P position, limit calculations and velocity commands are not modified by the smoother.

## Finding B — Ramping status was incorrectly motion-dependent

The canonical status resolver used position-in-ramp plus signed velocity direction. This meant a stationary skate inside the same geometrical ramp zone became `System | Active`.

The corrected resolver treats the ramp as a physical position zone. Near/Far Limit remain the more-specific endpoint states inside 1.0 m. Otherwise, a position inside either configured end ramp produces yellow `System | Ramping`, including at zero speed. Safety/service state priority remains unchanged.

## Finding C — W1P Encoder / EL7-RS path is implemented and guarded

The current W1P path was traced from SRVR position-source selection through UDP settings/VEL commands, EdgeBox RS485, Modbus transactions, drive configuration, feedback and safety gating.

Verified source contracts include:

- EdgeBox UART1 isolated RS485: TX=GPIO17, RX=GPIO18, RTS=GPIO8, hardware half-duplex.
- Leadshine Modbus address 1 and expected serial parameters 115200 / 8N1.
- Configuration verification for P00.01 PR internal command mode, P05.29 serial format, P05.30 baud and P05.31 node address.
- PR velocity path using P09.00 mode, signed P09.03 velocity, P09.04/P09.05 accel/decel and P08.02 path trigger/emergency stop.
- Position/I/O feedback using the P08.44/P08.45 32-bit position and adjacent input/output I/O words.
- Velocity command is written successfully before the PR trigger is sent, preventing a trigger from reusing an old velocity when a write fails.
- SRVR Encoder mode accepts W1P `POS_M` and signed `VEL_MPS`; Virtual mode is explicitly isolated.
- SRVR continually converges motor direction, units-per-metre, span, Near/Far, service mode and motion-profile settings until W1P STATUS confirms them.
- W1P independently gates drive writes on firmware/session health, E-stop, SRVR presence, RS485/configuration/feedback validity, Servo Ready, joystick freshness and local soft-limit protections.
- Independent 500 ms VEL freshness watchdog remains unchanged.

Conclusion: the software path is ready for controlled Encoder-mode commissioning. This does not substitute for real-drive commissioning; physical RS485 polarity/reference wiring, EL7 parameter state, motor/brake wiring, Servo Ready and mechanical scaling must still be checked on hardware.

## Regression updates

- Added `tools/test_bench_regression_0608.py` and included it in `run_all_source_checks.py`.
- Updated only historical assertions whose old velocity-prediction or motion-only-Ramping requirements were explicitly superseded by this revision.
- Extended the PySide runtime fixture so Ramping is asserted both while moving and while stopped inside the ramp zone.

## Verification result

`tools/run_all_source_checks.py`: PASS

- EdgeBox source integration: 370 checks PASS.
- Historical updater/RS485/safe-update/calibration/motion regressions: PASS.
- `.06.08` regression: PASS.
- Leadshine commissioning contract: PASS.
- Build pipeline: 53 checks PASS.
- Modbus/wire/speed/motion contracts: PASS.
- Release consistency/source hygiene/Python syntax/SRVR preflight: PASS.
- PySide runtime test is skipped only where PySide6 is not installed; desktop CI remains authoritative.
- Native Arduino/frozen desktop builds remain GitHub Actions gates.
