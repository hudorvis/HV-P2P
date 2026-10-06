# HV P2P v26.10.06.04 change summary

Date: 2026-10-06

Locked baseline: `v26.10.06.03`. This revision changes only automatic firmware-update recovery/diagnostics. The `.06.02` motion/UI fixes and all W1P/Leadshine safety architecture remain locked.

## Bench symptom addressed

- CTRL did not always begin the new release until a manual reboot.
- After CTRL updated, CTRL-TS could remain on the older firmware and sit on `Waiting for SRVR`.
- SRVR showed CTRL/CTRL-TS RS485 as Disconnected even though CTRL update progress had visibly reached the touchscreen.

## Root causes / architecture gaps

1. SRVR built the stage-1 `SRVR_FW` CTRL release beacon by evaluating the later W1P/CTRL-TS coordinator first. A later-stage coordinator exception/state problem could therefore suppress the CTRL release announcement itself. This inverted the intended dependency: CTRL must be stage 1 and must never depend on W1P/CTRL-TS state.
2. The SRVR communications worker and HMI-status receive path had no per-operation exception containment around firmware coordination. A single unexpected coordinator exception could terminate/skip the recurring release/recovery service and make a field-node reboot appear to fix discovery.
3. CTRL-TS final-stage permission had only SRVR-side recovery. A proven safe-OTA, hardware/protocol-correct older touchscreen could still remain stranded if `ts_allowed` failed to converge at the CTRL side.
4. SRVR's RS485 indicator represented *compatible HMI session*, not raw physical RS485 activity. During a legitimate version mismatch, HELLO/update frames could be flowing while the UI misleadingly displayed `Disconnected`.

## v26.10.06.04 corrections

- CTRL release beacons now use a fail-safe wrapper: later-stage coordinator failure keeps `ts_allowed=0` but cannot prevent the CTRL release/version beacon itself being transmitted.
- SRVR background CTRL/W1P beacon/recovery services and CTRL `HMI_STATUS` processing recover from individual exceptions instead of silently losing the communications worker.
- W1P still receives the preferred second-stage opportunity. A non-flashing/safe-idle-blocked W1P has an 8 s ordered wait; a genuinely active W1P update receives up to 60 s.
- CTRL adds an independent 12 s final-stage recovery. After CTRL itself is exact/matched, SRVR is online, the touchscreen has repeatedly proven the approved hardware/protocol and `safe_ota>=2`, and the target identity is still mismatched, CTRL may start the independent CTRL-TS update even if the coordinator grant remains stuck. W1P remains fail-closed if it is still mismatched.
- SRVR now distinguishes physical CTRL↔CTRL-TS RS485 activity from firmware compatibility. A live older touchscreen can show RS485/Link `Active` while its Firmware field reports the older version/update-required state.

## Preserved behavior

- Preferred update order remains CTRL -> W1P -> CTRL-TS.
- CTRL-TS image size/SHA verification, safe headless self-update, REBOOT ACK/retry and reboot-identity proof are unchanged.
- W1P independent 500 ms VEL watchdog and normal ~150 ms SRVR VEL refresh are unchanged.
- `.06.02` Limit Calibration, short System labels, AUX `None` ordering, smooth CTRL-TS progress marker and System-tab layout changes are unchanged.
- AI0 E-stop / AI1 joystick mapping, predictive/dynamic limits, hard limits and Leadshine velocity architecture are unchanged.

## Verification

All source/static/regression/preflight checks pass, including the new `test_firmware_rs485_recovery_0604.py`, 370 EdgeBox integration checks and 53 build-pipeline checks. Native ESP32 and frozen desktop/PySide compilation remain GitHub Actions gates; no local firmware binaries are fabricated.
