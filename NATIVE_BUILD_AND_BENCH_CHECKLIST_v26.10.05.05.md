# HV P2P v26.10.05.05 Native Build and Bench Checklist

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
