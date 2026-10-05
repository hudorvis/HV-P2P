# HV P2P v26.10.05.06 native-build and bench checklist

## v26.10.05.06 priority checks

- Start v26.10.05.06 SRVR while an older modern CTRL and CTRL-TS are already running. Do **not** reboot either ESP32. Confirm CTRL begins its pull update or SRVR begins the verified fallback automatically within a few seconds.
- After CTRL becomes current, confirm an older `safe_ota=2` CTRL-TS (including `.04.07`) automatically enters the two-stage safe update without a manual CTRL/CTRL-TS reboot.
- During the touchscreen's headless black phase, do not power-cycle it. Confirm CTRL retries the post-verify reboot handshake and the new touchscreen application returns automatically.
- Confirm a stale/absent W1P does not strand CTRL-TS at `Waiting for CTRL`; an actively updating W1P may briefly defer the display stage.
- Verify SRVR AUX Assign ordering: general alphabetical -> Near -> Ref -> Far -> Preset Recall -> Preset Save -> Preset Slip.

## Release gate

1. Require `ALL_SOURCE_CHECKS_PASS` from the final `.05.05` source layout.
2. Run GitHub Actions and require `python -m tools.test_backend_logic` to pass with PySide6 installed.
3. Native firmware/desktop compilation remains authoritative in GitHub Actions.

## Current Speed regression

In Virtual mode and later in safe unloaded hardware testing:

- command motion in both directions;
- SRVR Current Speed must always display a positive magnitude;
- CTRL-TS Current Speed must always display a positive magnitude;
- DSP1/HMM1 transport must retain a negative speed value for reverse motion and a positive value for forward motion;
- motion direction and predictive stopping must remain unchanged.

## Existing `.05.04` acceptance

Repeat the `.05.04` calibration/updater/UI bench checklist as needed; this hotfix does not intentionally alter those paths.