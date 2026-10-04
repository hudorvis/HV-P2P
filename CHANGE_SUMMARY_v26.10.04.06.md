# HV P2P v26.10.04.06 change summary

Date: 2026-10-04

Authoritative lineage: `HV P2P v26.10.04.05 - GitHub Ready Source.zip` -> this `.04.06` update-startup, post-update state convergence, Limit Calibration and Battery Change safety correction.

## 1. Firmware authority startup without manual reboot

A running older CTRL can receive the new SRVR release beacon before the SRVR firmware-authority HTTP endpoint is fully ready. The old behaviour attempted the manifest immediately, then could sit on a five-second retry and appear idle. `.04.06` adds a 15-second startup discovery window with 500 ms manifest retry after a new mismatched SRVR session/release is announced. The existing SRVR legacy-compatible background push remains available for older connected CTRL firmware.

CTRL-TS self-flash remains intentionally headless/display-off. CTRL and W1P progress can be displayed on CTRL-TS. Immediately before CTRL-TS self-flash, the application shows the safe-updater handoff; during the actual flash-write phase SRVR remains the authoritative live percentage display. This release does not re-enable LVGL/RGB during self-flash.

## 2. Post-update CTRL-TS state convergence

The update dashboard previously suppressed normal main-UI packets. CTRL could regard one-shot `HMS1`/`HMG1` deltas as delivered even though CTRL-TS intentionally did not apply them while the firmware screen owned the panel. That could leave the returning main UI with generic AUX labels and missing Ref/ramp/preset geometry until another unrelated state change occurred.

`.04.06` now:

- caches the latest bulk `HMI1`, compact state `HMS1` and geometry `HMG1` packet while firmware UI owns the panel;
- replays the latest snapshots immediately when the normal main UI returns;
- refreshes `HMS1` at 1 s and `HMG1` at 2.5 s as low-bandwidth self-healing keepalives;
- redraws live position, Ref, ramp and preset markers after replay;
- retains the single-flight POLL/EVENT RS485 scheduler.

A second firmware-screen bug is also fixed: repeated inactive firmware keepalives can no longer extend the return-to-main timer indefinitely. The two-second release timer is scheduled once on the real Active->Complete transition.

## 3. Limit Calibration wizard now matches Joystick Calibration

The SRVR Limit Calibration popup is rebuilt around the approved Joystick Calibration layout:

- same 720 x 540 panel structure;
- three steps only: Set Near -> Set Far -> Set Ref;
- Side View cable-position diagram in the central visual area;
- Near / Ref / Far captured-value boxes beneath the graph;
- live Current Position readout;
- matching Cancel / Back / primary action footer.

The final Ref capture now completes and closes the wizard immediately. There is no fourth `Done` step.

## 4. Battery Change safety after Limit Calibration

Completing Limit Calibration always returns Battery Change Mode to Off, clears the service excursion latch, closes calibration ownership, synchronises W1P service state, persists the configuration and returns normal Near/Far limit enforcement.

## Verification

Added `tools/test_bench_regression_0406.py` covering:

- fast firmware-authority startup retry;
- periodic `HMS1`/`HMG1` convergence;
- firmware-screen packet caching and replay;
- non-extending firmware-screen release timing;
- three-step Limit Calibration UI and backend flow;
- Battery Change forced Off on Limit Calibration completion;
- preservation of the safe headless CTRL-TS self-flash architecture.

The complete source/static/preflight suite remains the release gate. GitHub Actions remains authoritative for native ESP32 and frozen desktop compilation; powered motion remains a bench commissioning gate.
