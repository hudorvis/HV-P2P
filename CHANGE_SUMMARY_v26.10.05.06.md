# HV P2P v26.10.05.06 change summary

Date: 2026-10-05

Authoritative lineage: `HV P2P v26.10.05.05 - GitHub Ready Source.zip` -> this updater-convergence/AUX-order revision.

## AUX Assign ordering

SRVR Settings -> AUX Assign is now ordered exactly as requested:

1. General actions alphabetically: Acceleration Mode, Battery Change Mode, Drive Mode, Joystick Calibration, Limit Calibration, None, Winch Calibration.
2. Near options: Near Limit Recall / Save / Slip.
3. Ref options: Ref Point Recall / Save / Slip.
4. Far options: Far Limit Recall / Save / Slip.
5. Preset Recall 1..10.
6. Preset Save 1..10.
7. Preset Slip 1..10.

## Firmware convergence hardening

Bench testing showed an older running CTRL could still require a manual reboot before release convergence, and an older `safe_ota=2` CTRL-TS such as `.04.07` could become stranded at `Waiting for CTRL` or in its black headless updater after CTRL had already updated.

- Modern CTRL/W1P pull remains first choice, but the verified SRVR push fallback grace period is reduced from 4.0 s to 2.5 s and the mismatch timer is self-established whenever a fresh older version is known.
- CTRL-TS final-stage permission now requires CTRL to be current first, but stale/missing W1P state cannot hold `ts_allowed=0` forever. A W1P update actively in progress still briefly defers CTRL-TS.
- Once CTRL-TS accepts the first authorised `FW_BEGIN` and requests its safe display-off reboot, CTRL latches that exact update authorization across the headless transition. The second-stage flash no longer depends on a transient coordinator grant remaining true while the panel is black.
- A new SRVR authority session or explicit SRVR-offline transition clears that continuation latch, so authorization cannot leak across sessions.
- The final verified-image `REBOOT` handshake is retried every 750 ms up to 8 times (bulk firmware replies retain the conservative 3 s / 5 retry policy). This specifically improves compatibility with older `.04.07` safe-updater firmware that does not yet have its own autonomous post-verify reboot fallback.

## Preserved architecture

The W1P 500 ms velocity freshness watchdog, SRVR ~150 ms non-zero VEL refresh, AI0 E-stop / AI1 joystick mapping, hard-limit and predictive stopping logic, Leadshine velocity control, CTRL-TS single-flight RS485 scheduler, safe headless self-flash architecture, AUX delivery semantics and approved SRVR/CTRL-TS UI behavior are otherwise unchanged.

## Verification

The final versioned source must pass the complete source/preflight suite. GitHub Actions remains authoritative for native ESP32 and frozen desktop compilation.
