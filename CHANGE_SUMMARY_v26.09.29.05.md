# HV P2P v26.09.29.05 change summary

This is a focused CI regression-test hotfix built directly from v26.09.29.04. No runtime CTRL, W1P, CTRL-TS, RS485, motion, safety, OTA, or approved UI behaviour is intentionally changed.

## Fixed

- Corrected `SRVR_GitHub_v26.09.29.05/tools/test_backend_logic.py` after the commissioned default CTRL joystick direction was changed to **Inverted**.
- The Not-Calibrated 5 km/h test now validates speed magnitude rather than incorrectly requiring a positive sign.
- The Near-limit test now generates the correct outward command regardless of the configured/default joystick inversion.
- Added an explicit regression assertion that a new/reset installation defaults `reverse_joystick=True`.
- Bumped matched release/version metadata to v26.09.29.05 and the macOS bundle build number to `2609.29.2`.

## Unchanged

All v26.09.29.04 functional changes remain unchanged, including AI0 E-Stop / AI1 joystick mapping, filtered joystick acquisition, 500 ms W1P VEL watchdog, 150 ms SRVR VEL refresh, RS485 hardening, Leadshine fixes, CTRL-TS OTA progress/recovery, and locked Run/Setup UI design.
