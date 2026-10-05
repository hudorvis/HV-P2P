# HV P2P v26.10.05.06 deep code audit

Date: 2026-10-05

## Scope

Focused re-audit of SRVR firmware coordination, CTRL SRVR-authority OTA, CTRL -> CTRL-TS RS485 updater transitions, cross-version `.04.07` safe-updater behavior, and SRVR AUX Assign ordering.

## Confirmed failure mechanisms

### 1. CTRL update could still depend on reboot-created timing

Modern field firmware is designed to pull the immutable SRVR authority image. SRVR already had a push fallback, but its four-second grace window and dependence on previously-established mismatch timing left unnecessary room for a running older CTRL to appear idle until a reboot changed timing. v26.10.05.06 uses a 2.5 s grace and self-establishes the mismatch timer whenever a fresh older identity is available. The fallback remains background/asynchronous and upgrade-only.

### 2. W1P status could strand the final CTRL-TS stage

`_ctrl_ts_update_allowed()` previously returned false whenever W1P appeared connected but was not simultaneously firmware-current/fresh. A stale or partially-connected W1P could therefore prevent CTRL-TS update forever even after CTRL was correct. The actual hard dependency is CTRL first, because CTRL owns the staged touchscreen image and RS485 updater. v26.10.05.06 therefore defers the display only while W1P update activity is actually in progress.

### 3. Safe-reboot second stage unnecessarily re-depended on coordinator state

`.04.07` correctly stages a no-init-RAM handoff and deliberately reboots into a headless updater after the first `FW_BEGIN`. CTRL reset its transfer state on the expected `fw_safe_reboot_retry` response. Although the SRVR grant is repeated, the second `FW_BEGIN` still depended on that grant being true at the exact post-reboot discovery window. v26.10.05.06 latches a `g_hmiSafeUpdateContinuation` only after the first authorized handoff is accepted. That latch survives the touchscreen's safe reboot but is cleared by a new SRVR session/offline transition and by proof of the updated identity.

### 4. Older `.04.07` receiver has no autonomous final reboot

After a fully verified inactive image, `.04.07` waits for CTRL's `REBOOT` frame. If that final exchange is lost it can remain black/headless. CTRL already retried, but on the generic 3 s firmware timeout. v26.10.05.06 retains 3 s for firmware block/result traffic while retrying only the final reboot handshake at 750 ms, up to eight attempts.

## AUX ordering

The Setup `auxChoices` list now follows the requested operator grouping: general alphabetical actions, Near, Ref, Far, Preset Recall, Preset Save, Preset Slip. No action semantics changed.

## Safety review

No change was made to W1P motion/watchdog logic, Leadshine Modbus velocity control, E-stop/hard-limit protections, predictive/dynamic soft limits, or the CTRL-TS half-duplex single-flight scheduler.
