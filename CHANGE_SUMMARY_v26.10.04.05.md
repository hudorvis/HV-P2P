# HV P2P v26.10.04.05 change summary

Date: 2026-10-04

Authoritative lineage: `HV P2P v26.10.04.04 - GitHub Ready Source.zip` -> this `.04.05` updater-startup, calibration-visibility, geometry-sync and CTRL-TS AUX-authority correction.

## CTRL-TS update startup and safe self-flash handoff

Two update behaviours are deliberately separated.

- A running older CTRL no longer has to be manually rebooted before SRVR notices it needs firmware. A fresh CTRL `HMI_STATUS` is now enough for SRVR to schedule the legacy firmware push from the receiver path, with a thread-safe reservation and paced retry guard.
- CTRL-TS self-flash remains intentionally headless. The known-safe updater does not initialise RGB/LVGL/touch/PSRAM while programming its own application partition. `.04.05` therefore does **not** pretend that the physical CTRL-TS can show its own 0–100% flash percentage safely.
- Before that deliberate black phase, CTRL-TS now displays `Preparing safe updater - SRVR shows self-flash progress` for about 1.8 s. CTRL suppresses HMI rediscovery for about 3.0 s so the handoff cannot race the reboot.
- CTRL and W1P progress remain displayable on CTRL-TS before the self-update handoff. During CTRL-TS's own headless write, SRVR remains the exact percentage display.

Showing live CTRL-TS self-flash progress on the same panel would require a different updater architecture (for example, a resident display-capable bootloader or another staged/apply design), not simply turning the production LVGL UI back on during flash.

## Canonical uncalibrated wording and joystick-neutral display

The operator status text is now exactly `System | Uncalibrated` wherever SRVR emits the uncalibrated system banner/state.

SRVR's operator-facing Joystick Value/Percentage readout now snaps to exactly `0.0%` while the calibrated input is inside the configured neutral/deadband window. This is display-only: raw ADC/calibration values, deadband behaviour and motion calculations are unchanged.

## Limit Calibration visibility, including Virtual mode

The Limit Calibration wizard now exposes the same kind of captured-position feedback as Joystick Calibration:

- `NEAR`
- `REF`
- `FAR`
- live `CURRENT POSITION`

SRVR exposes these values in the calibration popup and CTRL-TS displays them in its calibration overlay. The capture map is driven by live `stateChanged`, so Current Position continues updating while the Virtual simulator is moving.

Virtual Limit Calibration initialises a local position when required, can be moved by the normal simulated motion path, and preserves the captured Near/Ref/Far positions while advancing through the wizard. This does not send non-zero physical W1P velocity; Virtual mode still holds any connected W1P STOPped and software Servo Enable inhibited.

## CTRL-TS AUX assignment authority

The stale CTRL-TS labels `Accel Type / Goto Ref / AUX 5` were traced to persisted CTRL `UIL1` presentation data being allowed to overwrite live SRVR AUX assignments after reconnect.

`.04.05` makes ownership explicit:

- `UIL1` remains presentation/layout-only;
- CTRL's default layout uses generic `AUX 1` ... `AUX 5` placeholders;
- CTRL-TS ignores any AUX assignment fields received in `UIL1`;
- live SRVR state is the only authority for AUX assignment labels/semantics;
- reconnect explicitly re-queues the latest live state after layout delivery so stale NVS layout can never win the race.

## Dedicated change-driven HMI geometry packet

Ramp zones, Ref and presets no longer depend on a coincidental bulk HMI redraw. CTRL now creates a compact change-driven `HMG1` packet carrying:

- Near / Ref / Far geometry;
- normalized Near/Far ramp fractions;
- Ref visibility/fraction;
- preset names, positions and visibility.

`HMG1` uses the existing single-flight RS485 arbiter and is prioritised ahead of the ~900-byte bulk display packet. CTRL-TS explicitly redraws reference, ramps and presets on `HMG1`, and redraws them again when a calibration overlay closes.

The ordinary priority `HMS1` state packet remains sparse. Live position is **not** added to it during normal motion; the faster calibration position/captures are included only while a calibration wizard is active. This preserves event/POLL margin instead of turning the priority channel back into continuous telemetry.

## Verification

Added `test_bench_regression_0405.py` and extended backend runtime/static contracts for:

- canonical uncalibrated wording;
- joystick neutral readout;
- live/captured Limit Calibration values;
- Virtual Limit Calibration movement/capture;
- SRVR-owned AUX labels;
- `HMG1` geometry/preset transport and scheduler priority;
- running-old-CTRL automatic update scheduling;
- safe headless CTRL-TS updater handoff timings.

The complete source/static/preflight suite is the release gate. GitHub Actions remains authoritative for native ESP32 compilation and frozen desktop builds; powered motion remains a bench commissioning gate.

- CTRL-TS green active-state wording is now canonical `System | Active`; yellow uncalibrated remains `System | Uncalibrated`.
