# HV P2P v26.10.03.03 — CTRL ↔ CTRL-TS / SRVR runtime audit

Authoritative base lineage: `HV P2P v26.10.02.05 - GitHub Ready Source.zip`.

## Original CTRL ↔ CTRL-TS faults confirmed in .02.05

1. CTRL could send another 50 ms POLL while the previous POLL was outstanding, overwriting the expected sequence and causing a valid delayed EVENT to be rejected as stale.
2. CTRL could start a large HMI TEXT frame after a POLL without waiting for the EVENT response, allowing CTRL and CTRL-TS to transmit at the same time on the half-duplex RS485 pair.
3. Normal POLL/EVENT traffic lacked a transaction timeout; the 3 s HMI timeout was only a link-health timeout.
4. CTRL-TS removed an event before successful delivery was proven, so a lost/corrupt/stale EVENT permanently discarded the AUX action.
5. A roughly 900-byte display state at 10 Hz consumed most of the 115200-baud wire budget.
6. The CTRL-TS AUX/event path contained unnecessary dynamic `String` allocation.
7. Parser CRC/resynchronisation failures were not visible in diagnostics.

The `.03.01/.03.02` work introduced single-flight scheduling, EVENT ACK/retry semantics, fixed event buffers, parser counters and a 4 Hz bulk-display cap. GitHub native compilation then caught and `.03.02` corrected the CTRL-TS parser-name typo (`g_hmiParser` versus `g_rs485Parser`).

## Real-hardware findings after .03.02

### 1. 35 ms timeout could re-open the collision window

CTRL-TS services normal RS485 from the Arduino loop while coordinating with LVGL and the loop includes a 20 ms delay. Real render/mutex scheduling can therefore delay a valid POLL response beyond 35 ms. `.03.02` immediately released the master bus on timeout. A delayed slave EVENT could still start after that release, while CTRL had already begun another master transmission.

`.03.03` uses a 250 ms POLL response timeout. If it still expires, CTRL enters a 300 ms **master-silent recovery interval**. RX remains active, but POLL/HELLO/TEXT are suppressed until the quiet period ends. A late EVENT is not ACKed and therefore remains queued on CTRL-TS for a later clean retry.

### 2. Slow EVENT responses could starve master state traffic

Before `.03.03`, the next POLL was scheduled from the previous POLL transmit timestamp. If a response arrived after that interval had already elapsed, `handleHmiRx()` could immediately issue the next POLL before the main loop had a chance to send SRVR state. Repeated slow responses could therefore serialize the bus correctly yet still starve SRVR→CTRL-TS state updates.

`.03.03` refreshes the POLL cadence timestamp when a valid EVENT transaction completes. That creates a deterministic master-TX opportunity after the response. A compact `HMS1` state packet has priority over the large HMI1 packet, and a priority state frame suppresses bulk HMI1 transmission for that loop pass.

### 3. AUX delivery could be lost in the SRVR Qt thread

CTRL correctly converted an accepted AUX EVENT into the existing control-packet flag, but SRVR originally looked for the rising edge in `_motion_tick()`, a 25 ms Qt timer callback. `.03.02` also introduced a severe UI/log slowdown. If the Qt thread stalled for longer than the CTRL flag pulse, the network listener could receive both high and low while `_motion_tick()` saw only the final low state; the confirmed AUX command vanished before `_handle_aux_action()` ran.

`.03.03` performs AUX rising-edge capture in the background UDP receive thread and places the AUX index into a bounded persistent queue. `_motion_tick()` drains that queue and executes the existing action logic. The CTRL AUX compatibility latch is also 300 ms for both UDP and CTRL-TS-originated events. No W1P watchdog timing is changed.

### 4. SRVR diagnostic log storm caused compounding UI slowdown

The `.03.02` HMI_STATUS parser read cumulative RS485 counters, stored them, then reset the stored values to zero. Once any counter became non-zero, the same cumulative value looked new on every 250 ms HMI_STATUS report. SRVR repeatedly logged the same fault. Each `logChanged` caused the QML Log page model to be regenerated/refiltered, so cost increased as the log grew.

`.03.03` keeps cumulative baselines, compares against the last logged tuple, and rate-limits combined RS485 summaries to at most one every 2 seconds when a counter advances.

### 5. Auto-save performed durability I/O on the UI thread

Settings and Free-D correctly use auto-save, but `_save_config()` synchronously performed backup replacement, file `fsync()` and directory `fsync()` from the Qt UI thread. On Intel macOS those durability operations can visibly stall the interface during edits.

`.03.03` preserves auto-save while moving the atomic write/fsync work to a single-slot coalescing `HVP2P-ConfigWriter` daemon thread. The UI only queues the latest complete snapshot. Shutdown drains the queue before the writer exits.

### 6. CTRL-TS did not independently know that SRVR had disappeared

CTRL continued POLLing CTRL-TS after SRVR quit, so `last_hmi_rx` stayed fresh. `g_srvr_ok` was mainly updated from bulk HMI state and could remain latched true if the final SRVR-off state never arrived. The touchscreen therefore stayed on its normal dashboard.

Every `.03.03` POLL carries `P1|srvr=0/1`, based on CTRL's own SRVR display freshness. CTRL-TS reads this fixed field before its response but applies it only **after** its EVENT has left the UART, so UI work cannot delay the response. When the hint becomes false, the resident `Waiting for SRVR` state is restored even if bulk HMI1 is unavailable.

### 7. Black screen during CTRL-TS self-update is intentional

The safe updater deliberately reboots into a headless display-off path before writing its own OTA partition. LVGL/RGB/display initialization is avoided while self-flash is active. A physical black touchscreen together with SRVR showing `CTRL-TS Updating xx%` is therefore expected, not the symptom being debugged.

## Genuine reboot diagnosis

The reported AUX-confirm reboot still requires the next bench log to identify the ESP reset class conclusively. The transport/state defects above explain lost commands, stale state and collision risk, but should not be represented as proof of a particular ESP reset mechanism. CTRL-TS still reports a per-boot ID and `esp_reset_reason()`. `.03.03` additionally labels the numeric reason in SRVR logs (SOFTWARE, PANIC, TASK_WDT, BROWNOUT, etc.) so the next occurrence can be classified directly.

## Preserved safety/control architecture

W1P is unchanged apart from the release-version token. Its independent 500 ms VEL freshness watchdog remains intact. SRVR non-zero VEL refresh remains approximately 150 ms. AI0 E-stop / AI1 joystick mapping, hard limits, predictive stopping/dynamic soft limits, Leadshine velocity architecture, firmware authority and the approved UI remain intact.

## Regression/preflight coverage

The complete source runner includes the bus-serialization contract plus a new runtime-regression contract. It checks the timeout/recovery quiet gate, ACK/retry event semantics, no outstanding-POLL overwrite, compact state priority, completion-based poll cadence, independent SRVR presence hint, persistent AUX edge queue, diagnostics baseline retention, asynchronous config writer, reset-reason diagnostics and source hygiene.

Native Arduino compilation and frozen desktop packaging remain authoritative in GitHub Actions; physical RS485/display/reset behavior remains a bench gate.
