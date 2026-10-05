# HV P2P v26.10.05.03 deep code audit

Date: 2026-10-05

## Scope

Audit of the `.05.02` real-hardware update failure where CTRL did not begin updating until manually rebooted and, after CTRL reached `.05.02`, CTRL-TS remained on `.04.07` at `Waiting for CTRL` without beginning its staged RS485 update.

## Finding 1 — final-stage grant was coupled to presentation traffic

`hmiFwStart()` previously inferred final-stage permission from `g_latestDisplayPacket` by parsing `fw_ts_allowed`. That made firmware orchestration depend on receipt/timing of DSP1/HMI presentation state. A mismatched HELLO could be processed before the grant arrived; although HELLO retries normally recover, this coupling made convergence sensitive to reconnect/update-screen timing and provided no independent coordinator state.

### Correction

SRVR now repeats `ts_allowed` in the lightweight `SRVR_FW` beacon. CTRL stores the grant independently (`g_hmiTsCoordinatorSeen` / `g_hmiTsUpdateAllowed`), resets it on a new SRVR session, accepts the older DSP1 mirror for compatibility, and reports `ts_grant` in `HMI_STATUS`.

CTRL also timestamps each validated HELLO identity. While incompatible, if a fresh identity is a safe-OTA-capable approved CTRL-TS target, differs from the staged image, CTRL matches SRVR authority, and the coordinator grant is active, CTRL can call `hmiFwStart()` from the normal serialized HMI service loop. This removes the requirement for the grant and mismatch HELLO to coincide.

## Finding 2 — modern pull OTA had no fallback

For modern CTRL/W1P versions, SRVR deliberately stopped using the browser-upload bridge and relied entirely on each node's SRVR-authority pull. Bench testing showed a proven older node could remain mismatched until manually rebooted. That means the system needed a bounded recovery path rather than waiting indefinitely for another boot/session transition.

### Correction

SRVR tracks how long a proven older CTRL/W1P version remains mismatched. Normal pull/verify remains first choice. If the node has not entered `updating`/`rebooting` (or W1P safe-idle update state) after 4 seconds, SRVR starts the existing asynchronous `/update/app` upload using the already-validated immutable authority image. The worker remains off the Qt/motion thread and version ordering still prevents downgrades.

## Ordering/safety

The coordinator retains CTRL -> W1P -> CTRL-TS ordering. Motion is forced to zero while an older field node is converging. CTRL-TS final-stage permission is withheld until CTRL is current/fresh and W1P is either current/fresh or absent for the established discovery interval.

The CTRL-TS self-flash implementation itself is unchanged: normal UI stages a safe handoff, software-reboots to the headless updater, receives/verifies the staged image over serialized RS485, then reboots into the new application. Manual reset during that handoff can intentionally discard the retained RAM marker; normal operation should therefore be allowed to complete without manually rebooting CTRL-TS.

## Verification

`test_firmware_coordinator_0503.py` locks the repeated coordinator beacon, dedicated CTRL grant state, fresh-identity proactive start, modern pull-first fallback and ordered gate. Existing RS485 single-flight, firmware retry, target identity, safe-updater, motion and safety regressions remain enabled.
