# HV P2P v26.10.05.11 deep code audit

Date: 2026-10-05

## Scope

The audit covered the complete current release path across:

- SRVR startup/shutdown, Qt timer, controller listener, background communications worker, W1P UDP client and firmware coordinator;
- immutable firmware-authority server/bundle flow;
- CTRL release beacon handling, authority verification/OTA, CTRL-TS coordinator grant and RS485 touchscreen updater state machine;
- W1P authority verification/OTA and drive-safe update preparation;
- CTRL-TS safe updater, final image verification, boot partition selection, FW_RESULT, REBOOT and autonomous fallback reboot;
- GitHub native-build staging/embed pipeline and existing regression/preflight contracts.

The `.05.09 -> .05.10` functional diff was checked first. CTRL, W1P, CTRL-TS and `firmware_authority.py` were unchanged other than release identity; `.05.10` changed only the requested SRVR calibration display, QML System-row geometry and AUX display-field width. This ruled those three bench fixes out as direct updater breakage.

## Finding A — exact cause of `.05.10` automatic-update failure

SRVR had two separate notions of liveness:

1. `SRVR_ALIVE` had been moved to `_srvr_alive_worker()` so CTRL connection safety was independent of Qt/macOS focus scheduling.
2. `SRVR_FW`, W1P firmware beacons and the `ts_allowed` final-stage coordinator grant were still emitted from `_tick()`, a 25 ms Qt `QTimer` callback.

This split allowed CTRL to remain visibly connected from the background `SRVR_ALIVE` packets while never receiving the newer release announcement if Qt was delayed/stalled. The old CTRL therefore had no reason to enter its fail-closed manifest/OTA path.

The manual-reboot observation confirms the path: CTRL performs an independent boot-time authority manifest check, so rebooting it discovers the new release even without a timely `SRVR_FW` packet. CTRL-TS could remain old because its final `ts_allowed` grant was still dependent on Qt-driven coordinator traffic.

### Fix

`_srvr_alive_worker()` is now the background **communications** worker. It emits:

- `SRVR_ALIVE` at ~250 ms; and
- CTRL/W1P release/coordinator beacons at 500 ms.

`_tick()` no longer emits firmware beacons. The worker does not perform HTTP, flash or motion actions; field nodes continue to verify and install their own exact immutable images.

## Finding B — W1P update-order state also depended on Qt

The final CTRL-TS gate previously read W1P firmware state populated by `_parse_w1p()`, which only runs after the Qt timer drains `_w1p_rx`. Moving only the firmware beacon to a background thread would therefore leave a second Qt dependency in the CTRL -> W1P -> CTRL-TS state machine.

### Fix

`W1PClient` now parses only the lightweight firmware fields (`FW`, `FW_MATCH`, `FW_AUTH`) from complete STATUS packets in its own UDP receive thread and publishes a locked snapshot. It also recognizes W1P `FW_PROGRESS` packets, marking the firmware-order snapshot as updating/rebooting without ever allowing progress telemetry to claim `FW_MATCH`. This matters because the blocking OTA download can temporarily pause normal STATUS output. The normal authoritative safety/status parser is unchanged and still performs validate-before-commit on the Qt side.

The final-stage coordinator uses this network-thread snapshot for update ordering, so GUI scheduling cannot block convergence and a long W1P image transfer remains positively visible to the order gate.

## Finding C — normal startup could race W1P discovery

Once CTRL became current, a healthy W1P might not yet have delivered its first STATUS at the exact moment `_ctrl_ts_update_allowed()` ran. Treating "not seen yet" as "absent" could allow CTRL-TS to update before W1P.

### Fix

After CTRL has been exactly matched/fresh for one second, `.05.11` allows an additional bounded 3-second W1P discovery window. W1P is probed every 250 ms, so this is ample for a healthy local node while remaining harmless when W1P is genuinely absent.

If W1P was observed old/mismatched, a pending-order latch survives its OTA reboot. A 15-second bounded absence escape prevents a dead or physically absent participating W1P from permanently stranding CTRL-TS.

## Finding D — SRVR authority session token was not fully enforced on field nodes

The backend comment and session design intended every new SRVR process to cause one exact authority re-verification. However:

- CTRL reset coordinator grants on a new session but only invalidated its firmware match when the version changed.
- W1P ignored the session token for authority matching.

A same-version new SRVR process could therefore inherit a stale previous-session match without rechecking the exact bundled SHA.

### Fix

Both CTRL and W1P now treat a new SRVR session as an authority boundary. If previously matched, they fail closed, immediately re-fetch the manifest and re-hash the running image. An already exact image returns to matched without a flash; a same-version SHA mismatch enters the exact-image replacement path.

W1P stops locally and inhibits drive writes while re-verifying, preserving its existing fail-safe authority semantics.

## Finding E — graceful shutdown had a background-beacon ordering race

`shutdown()` correctly set `_stop_evt` before sending `SRVR_OFFLINE`, and `SRVR_ALIVE` re-checked the event inside the CTRL TX lock. The new firmware beacon initially did not perform the same under-lock check.

A worker that had passed its outer stop test but was blocked waiting for the lock could theoretically acquire the lock after OFFLINE and send one late `SRVR_FW`.

### Fix

CTRL firmware-beacon transmission now re-checks `_stop_evt` under `_ctrl_presence_tx_lock`. Therefore:

- a beacon already holding the lock completes before shutdown;
- shutdown then sends OFFLINE last; or
- a waiting beacon sees stop set and sends nothing.

This preserves the existing immediate CTRL-TS Waiting/Splash behavior when SRVR closes.

## CTRL / CTRL-TS final updater re-audit

The `.05.09` final-reboot fix remains intact:

- `FW_END` requires exact SHA/size and the touchscreen calls `Update.end(true)` to select the verified new OTA partition.
- CTRL-TS persists the target firmware identity per OTA partition.
- `FW_RESULT ok=1` is idempotent so a lost result can be recovered.
- REBOOT ACK is not treated as completion.
- CTRL enters `HMI_FW_WAIT_REBOOT_CONFIRM`, continues bounded reboot enforcement and HELLO discovery, and verifies the required version/SHA after restart.
- Legacy safe-updater firmware without a pre-update `boot_id` has an exact-identity reboot proof path.
- CTRL-TS retains an autonomous verified-image reboot fallback if the final REBOOT exchange is lost.
- During actual self-flash, RGB/LVGL is intentionally not initialized; the screen remains black/headless.

No `.05.11` change was required inside CTRL-TS firmware itself.

## Safety invariants reviewed

- W1P `W1P_VEL_COMMAND_TIMEOUT_MS = 500` unchanged.
- SRVR `VEL_KEEPALIVE_S = 0.15` unchanged.
- CTRL peer timeout remains 750 ms, with background `SRVR_ALIVE` independent of Qt.
- W1P STATUS safety arbitration remains validate-before-commit; malformed frames cannot erase the last good snapshot, but freshness timeout and genuine faults remain fail-safe.
- AI0 E-stop / AI1 joystick, joystick-neutral re-arm, Leadshine velocity mode, predictive/dynamic limits and hard-limit logic were not modified by `.05.11`.
- RS485 HMI framing/header remains byte-identical between CTRL and CTRL-TS.

## Regression hardening

`test_firmware_background_convergence_0511.py` now asserts that:

- the authority HTTP server starts before backend networking workers;
- release discovery runs in the background communications worker;
- Qt `_tick()` is not a firmware-discovery prerequisite;
- W1P firmware-order state is captured in the W1P network thread;
- W1P discovery/order latches are bounded;
- CTRL and W1P revalidate on new SRVR authority sessions;
- graceful shutdown prevents a post-OFFLINE firmware beacon; and
- 500 ms W1P watchdog / ~150 ms normal SRVR refresh / 750 ms CTRL peer timeout remain intact.

Older brittle tests that matched superseded local variable/debug-string text were updated to assert the actual preserved timing/state behavior instead.

## Remaining external gates

No static/source audit can guarantee that no future field issue is possible. The release is designed to remove the identified update races and adds regression coverage for them, but the authoritative remaining gates are:

1. GitHub Actions native ESP32 compilation/staging;
2. GitHub frozen desktop/PySide runtime jobs; and
3. physical bench verification of CTRL -> W1P -> CTRL-TS update convergence, RS485 self-update/reboot and real Leadshine motion safety.
