# HV P2P v26.10.06.03 deep code audit

Date: 2026-10-06

## Scope

`v26.10.06.02` is the locked baseline. The audit was restricted to the automatic-update regression reported after `.06.02`.

A normalized production diff between `.06.01` and `.06.02` confirmed that CTRL, W1P and CTRL-TS updater logic had not functionally changed. Therefore the observed failure was traced through the SRVR release-discovery/recovery coordinator rather than by modifying the proven flash protocol.

## Root cause 1 — modern pull fallback still depended on Qt

The normal modern path is:

1. background SRVR communications worker sends `SRVR_FW`;
2. stale CTRL/W1P invalidates its old authority match;
3. node pulls manifest/image from SRVR and verifies SHA/role/target;
4. node safely stages/reboots.

A second path already existed: after a 2.5 s mismatch grace, SRVR can upload the exact bundled image through the node's proven `/update/app` endpoint. That fallback was only evaluated by `_service_legacy_firmware_push()` from the Qt `_tick()` path.

If a modern node missed the primary pull or failed to enter it, a delayed/stalled Qt timer could leave the fallback unevaluated. Rebooting the node then appeared to fix the issue because boot-time authority discovery independently queried SRVR.

### Correction

`.06.03` adds `_service_firmware_recovery_background()` to the independent SRVR communications worker. It evaluates only recovery eligibility and launches the existing asynchronous verified HTTP worker. No flash I/O is performed in the communications loop.

A stale CTRL status also forces an immediate `SRVR_FW` retry, reducing reliance on the next periodic beacon.

## Root cause 2 — final CTRL-TS grant could be held forever by W1P

`_ctrl_ts_update_allowed()` correctly required CTRL to converge first and attempted W1P second. However, a present W1P that remained non-current—including `update_waiting_safe_idle`—kept returning false with no bounded final-stage release. This directly explains the observed state where CTRL displayed 100% while CTRL-TS remained `Waiting`.

### Correction

The intended order remains CTRL -> W1P -> CTRL-TS, but the coordinator is now bounded:

- CTRL exact/fresh authority match is still mandatory.
- Healthy/actively flashing W1P gets up to 120 s to finish.
- A present but non-flashing/non-converged W1P gets 30 s of ordered recovery attempts.
- If that bounded window expires, CTRL-TS is granted independently. W1P remains mismatched/fail-closed and continues receiving authority beacons/recovery attempts; this grant does not enable motion or weaken W1P safety.
- Once granted for this SRVR release, the CTRL-TS final-stage grant is monotonic, avoiding transient W1P status changes revoking an in-progress final update.
- The existing absent-W1P and W1P-reboot handling remains in place.

## Whole update-chain review

Rechecked without functional change:

- SRVR authority server starts before backend/network workers.
- CTRL/W1P release/session invalidation and exact SHA re-verification.
- CTRL -> W1P -> CTRL-TS preferred ordering.
- CTRL-TS staged image identity, size and SHA checks.
- `Update.end(true)` boot partition selection.
- `FW_RESULT` idempotence and REBOOT ACK/retry handling.
- post-reboot exact version/SHA/boot identity convergence.
- safe headless CTRL-TS self-update and autonomous fallback reboot.
- single-flight half-duplex RS485 arbitration.

## Locked production diff

After normalizing version strings, only SRVR `backend.py` differs functionally from `.06.02`. CTRL, W1P, CTRL-TS, QML and `firmware_authority.py` are unchanged.

## Verification

The complete source/static regression suite passes, including:

- 370 EdgeBox integration checks;
- all historical updater/RS485/calibration/bench contracts through `.06.02`;
- new `.06.03` automatic-update recovery contract;
- 53 build-pipeline checks;
- Modbus, wire, speed and motion contracts;
- release consistency, source hygiene and Python syntax; and
- SRVR project preflight.

PySide runtime and native firmware compilation remain GitHub Actions gates. Physical update convergence remains a bench gate.
