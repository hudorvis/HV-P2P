# HV P2P v26.10.06.04 deep code audit

Date: 2026-10-06

## Locked baseline

`v26.10.06.03` is the locked baseline. The audit was restricted to the reported automatic-update/RS485-status regression.

## What the bench symptom proves

The touchscreen visibly rendered CTRL firmware-update progress before CTRL rebooted. That progress is sent over CTRL↔CTRL-TS RS485, so the physical bus was proven operational at that point.

After reboot, an older CTRL-TS is intentionally *not compatible* with the new CTRL until version/SHA match. CTRL therefore reports `ctrl_ts=0` even while HELLO/identity traffic may still be flowing. SRVR previously used that compatibility bit for its RS485/Link indicator, which explains the apparently contradictory `RS485 Disconnected` display.

## Update-chain audit

The intended dependency is one-way:

1. SRVR announces release to CTRL.
2. CTRL verifies/updates and re-matches.
3. W1P is attempted.
4. CTRL-TS is final.

In `.06.03`, `_send_ctrl_firmware_beacon()` called `_ctrl_ts_update_allowed()` while constructing the CTRL release packet. That couples stage 1 to stages 2/3/4. If later-stage coordination throws or becomes pathological, CTRL can miss the release announcement even though it should be independent. Manual CTRL reboot then uses boot-time authority discovery, matching the observed recovery behavior.

The same later-stage logic was also called from recurring background communications without per-operation exception containment. The fix makes release discovery self-healing rather than relying on a perfect coordinator path forever.

## CTRL-TS recovery

Normal SRVR `ts_allowed` ordering remains authoritative first. CTRL now also records how long a safe-OTA approved mismatched touchscreen has been continuously identified after CTRL itself is authority-matched. If the mismatch persists for 12 s with SRVR online and a valid authority session, CTRL may begin the independent touchscreen final stage. This fallback cannot enable W1P motion and does not bypass hardware/protocol/safe-OTA/image integrity checks.

## RS485 status semantics

Safety compatibility remains unchanged: `hmiLinkConnected()` still requires exact compatible HMI identity. A new SRVR-only `ctrlTsRs485Active` diagnostic is derived from fresh HMI status age/identity traffic and is used by the Setup RS485/CTRL-TS Link indicators. This separates physical transport health from release compatibility without weakening any safety gate.

## Whole-program preservation

The W1P 500 ms VEL watchdog, Leadshine Modbus architecture, CTRL AI0/AI1 mapping, limit protections, single-flight EVENT ACK/retry path, safe display-off CTRL-TS updater, calibration transactions and `.06.02` UI/motion fixes remain unchanged.

## Verification

- all historical top-level source regressions: PASS;
- `test_firmware_rs485_recovery_0604.py`: PASS;
- EdgeBox integration validator: 370 checks PASS;
- build-pipeline validator: 53 checks PASS;
- SRVR project preflight: PASS;
- source hygiene/release consistency/Python syntax: PASS.

Native ESP32 and frozen desktop/PySide compilation remain GitHub Actions gates.
