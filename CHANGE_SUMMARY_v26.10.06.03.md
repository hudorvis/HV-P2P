# HV P2P v26.10.06.03 change summary

Date: 2026-10-06

Locked baseline: `v26.10.06.02`. This revision is limited to the reported automatic firmware-update regression. The five `.06.02` operator/motion/UI changes remain unchanged.

## Reported bench symptom

With `.06.02` SRVR, the automatic release update did not reliably start by itself. Rebooting CTRL caused CTRL to discover and install `.06.02`, but CTRL-TS could remain on the previous release with its firmware dashboard showing CTRL at 100% and CTRL-TS still `Waiting`.

## Audit result

A normalized `.06.01 -> .06.02` production diff proved that CTRL, W1P and the firmware-update state machines did not change in `.06.02`; the only SRVR backend functional delta was the Limit Calibration VEL-lease renewal. The field symptom exposed two pre-existing recovery/coordinator gaps rather than a direct change to the flash protocol:

1. Modern CTRL/W1P normally pull the new image after the background `SRVR_FW` beacon. The verified HTTP push fallback for a node that missed/failed that pull was still *evaluated only from the Qt/UI tick*. A node could therefore stay stale until a reboot triggered its boot-time authority check.
2. CTRL-TS was correctly ordered last, but a present W1P that stayed in a non-current state (including `update_waiting_safe_idle`) could keep `fw_ts_allowed=0` indefinitely. This could leave CTRL at 100% while CTRL-TS remained `Waiting` forever.

## `.06.03` correction

- Firmware fallback eligibility is now evaluated by the same background communications worker that owns `SRVR_ALIVE` and `SRVR_FW`; recovery no longer depends on Qt rendering/timer progress.
- Any fresh HMI status proving CTRL is on an older release immediately triggers another authority beacon as well as the normal 500 ms beacon stream.
- After the existing 2.5 s modern-pull grace, SRVR may start the already-existing verified `/update/app` fallback from a daemon thread without requiring a CTRL/W1P reboot.
- Before a W1P fallback attempt, the SRVR-side background VEL bridge is cleared and `STOP` is queued. W1P still independently refuses flash unless its own stopped/braked service gate succeeds.
- CTRL-TS final-stage permission is monotonic once granted for the current SRVR release.
- The intended order remains CTRL -> W1P -> CTRL-TS. A healthy/actively flashing W1P is given up to 120 s to complete. A W1P that is present but cannot converge (for example waiting for safe idle) is given a 30 s ordered recovery window; after that, only the independent CTRL-TS stage is released while W1P remains firmware-mismatched/fail-closed and continues retrying separately.
- A W1P that disappears during its ordered reboot retains the existing bounded absence handling.

## Locked scope

After normalizing release strings, the only production file with functional changes from `v26.10.06.02` is:

- `SRVR_GitHub_v26.10.06.03/backend.py`

Run QML, Settings QML, CTRL firmware, W1P firmware, CTRL-TS firmware, firmware-authority server and all motion/safety logic are unchanged apart from release identity.

## Preserved `.06.02` fixes

- Limit Calibration background VEL bridge renewal from coherent fresh CTRL input.
- Short Run/System calibration captions: `Joystick`, `Limit`, `Winch`.
- AUX Assign `None` first.
- CTRL-TS local smooth progress-marker interpolation.
- Run/System grid geometry aligned to neighbouring Shortcut tabs.

## Preserved safety contracts

- W1P independent VEL watchdog: 500 ms unchanged.
- Normal SRVR non-zero VEL refresh: approximately 150 ms unchanged.
- AI0 E-stop / AI1 joystick mapping unchanged.
- Joystick-neutral re-arm unchanged.
- Predictive/dynamic soft limits, hard limits and Leadshine velocity architecture unchanged.
- CTRL <-> CTRL-TS single-flight RS485 EVENT ACK/retry and safe self-update protocol unchanged.

## Regression coverage

New `tools/test_firmware_autoupdate_recovery_0603.py` requires:

- background update-recovery evaluation;
- immediate stale-CTRL authority beacon retry;
- modern fallback support for both CTRL and W1P;
- bounded W1P final-stage wait with monotonic CTRL-TS grant; and
- preservation of all `.06.02` requested fixes.

All source/static/regression/preflight checks pass. Native ESP32 and frozen desktop compilation remain GitHub Actions gates; no local firmware binaries are fabricated.
