# HV P2P v26.10.06.07 change summary

Date: 2026-10-06

Locked baseline: `v26.10.06.06`.

This revision changes only automatic firmware-release recovery and CTRL-TS connection/splash arbitration. Motion control, calibration logic, AUX behavior, limits, Leadshine/W1P safety, Run/Settings UI and the `.06.05` status states remain unchanged.

## Bench issues addressed

### 1. CTRL required a manual reboot before discovering the new SRVR release

The normal `SRVR_FW` release beacon is sent from SRVR to CTRL on a separate outbound UDP path. If that datagram is missed, a running CTRL that is already marked firmware-matched does not perform periodic HTTP authority checks by design, so it can remain on the old release until a reboot clears its match state. Boot-time authority discovery then makes the reboot appear to "fix" the update.

`.06.07` adds a redundant `SRVR_FW` datagram on CTRL's proven heartbeat return path. SRVR still replies with the normal one-byte heartbeat ACK, then at the normal firmware-beacon cadence sends the same release/session/final-stage grant back to the exact `(IP, port)` from which CTRL's heartbeat arrived. The original background beacon remains intact. Either path can now invalidate a stale CTRL authority match.

### 2. CTRL updated but CTRL-TS remained old / Waiting for CTRL

The CTRL-local 12-second final-stage recovery was intended to update an approved `safe_ota>=2` touchscreen even when the SRVR coordinator grant was lost. However, both the mismatch timer and the fallback additionally required `g_srvrFirmwareSession.length()`. If the missing `SRVR_FW` beacon was the original problem, that session token could also be missing after CTRL reboot, recreating the same deadlock.

`.06.07` removes only that optional session-token requirement from the bounded local fallback. The fallback still requires:

- CTRL exact SRVR firmware authority match;
- live SRVR heartbeat/presence;
- repeated CTRL-TS identity discovery;
- exact approved Waveshare hardware/protocol;
- `safe_ota>=2` capability;
- mismatched version/SHA for at least 12 seconds.

### 3. CTRL-TS could remain frozen at `CTRL | ... | 100%`

CTRL's final `FWSTAT ... active=0` completion status is sent immediately before CTRL reboots. That last RS485 status can be lost at the reboot boundary, leaving the external CTRL progress row marked active forever.

A post-reboot `HELLO_REQ` now proves CTRL has returned to its application and clears any stale active CTRL progress row to `Complete | 100%`. This does not affect the CTRL-TS self-update state machine.

### 4. CTRL-TS could flash between Home and the Waiting splash after SRVR closed

Two presentation races were found:

- releasing the firmware dashboard unconditionally loaded the main operating screen for one loop even when CTRL/SRVR was offline;
- a stale/in-flight HMI status packet with `srvr=1` could briefly override CTRL's much fresher POLL health hint `srvr=0`.

`.06.07` makes firmware-screen release connection-aware and makes the live POLL hint the freshest SRVR-presence authority. A stale positive HMI status can no longer resurrect Home while POLL says SRVR is offline.

## Locked behavior preserved

- W1P independent 500 ms VEL watchdog unchanged.
- Normal SRVR non-zero VEL refresh remains approximately 150 ms.
- AI0 E-stop / AI1 joystick mapping unchanged.
- Predictive/dynamic soft limits and hard-limit protection unchanged.
- Leadshine velocity/Modbus architecture unchanged.
- Transactional Joystick/Limit/Winch calibration unchanged.
- `.06.05` two-fresh-tap confirmation and rapid double-tap handling unchanged.
- `System | Ramping`, `System | Near Limit`, and `System | Far Limit` unchanged.
- `.06.02` UI/layout/progress-marker fixes unchanged.

## Verification

All source/static/regression/preflight checks pass, including 370 EdgeBox integration checks, all previous firmware/RS485/safe-updater contracts, the new `test_firmware_splash_recovery_0607.py`, 53 build-pipeline checks, release consistency, source hygiene, Python syntax and SRVR preflight.

Native ESP32 and frozen desktop compilation remain GitHub Actions authoritative. No local firmware binaries are fabricated.
