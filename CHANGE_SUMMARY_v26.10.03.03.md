# HV P2P v26.10.03.03 change summary

Date: 2026-10-03

Authoritative lineage: the approved `v26.10.02.05` source, followed by the `.03.01/.03.02` CTRL↔CTRL-TS serialization work. This revision addresses the first real-hardware feedback from `.03.02` without changing the approved operator UI or W1P/Leadshine motion architecture.

## Bench findings addressed

- A completely black CTRL-TS while it is programming its own flash is **intentional**. The safe updater reboots into a display-off/headless mode and does not initialize LVGL/RGB while `Update.write()` is active. SRVR remains the progress display during that phase.
- The `.03.02` normal POLL timeout of 35 ms was too aggressive for real Waveshare/LVGL scheduling. CTRL could abandon a POLL while CTRL-TS was still preparing a delayed EVENT, then reuse the bus and recreate a late-response collision window.
- `.03.02` reset the SRVR's stored cumulative RS485 fault counters after parsing them. Any non-zero fault was therefore logged again every 250 ms forever. Each log update forced QML to rebuild/refilter the log model, producing a compounding UI slowdown.
- CTRL converted accepted AUX events into a short flag pulse while SRVR detected the edge on the Qt UI timer. A UI stall could span the whole pulse, so Battery Change/Drive Mode/Calibration could be confirmed on CTRL-TS yet never execute in SRVR.
- Critical SRVR state changes (Drive Mode, Battery Change, calibration state) relied mainly on the large HMI display frame, so a congested link could leave CTRL-TS displaying stale state.
- CTRL-TS considered the CTRL link alive because POLLs continued even after SRVR quit. The last `srvr=1` display state could remain latched, leaving the normal UI visible instead of returning to `Waiting for SRVR`.

## v26.10.03.03 changes

- Normal POLL response timeout increased to **250 ms** and a **300 ms master-silent recovery window** is enforced after timeout. CTRL continues receiving during recovery but does not drive the RS485 pair, allowing a genuinely late slave EVENT to finish without collision.
- POLL cadence is now measured from **transaction completion** as well as request scheduling. A slow EVENT response cannot cause an immediate next POLL that starves pending master state traffic.
- Full display forwarding remains capped at **4 Hz**. A new compact priority `HMS1` state packet carries operator-critical state ahead of the bulk display packet.
- Only one priority/bulk normal HMI frame is emitted per CTRL loop pass, giving the scheduler another chance to service EVENT polling before a second bulk transfer.
- Every POLL carries a tiny `srvr=0/1` health hint. CTRL-TS updates its SRVR-presence state after transmitting its EVENT response, so SRVR loss is detected independently of bulk HMI delivery and the resident `Waiting for SRVR` screen can return.
- CTRL-TS EVENT delivery remains ACK/retry-safe with event IDs, duplicate suppression and fixed buffers. Touch-originated AUX latches are 300 ms, and SRVR now captures AUX rising edges persistently in the UDP listener thread before the Qt event loop can stall.
- SRVR RS485 diagnostics retain their cumulative baselines and emit a compact fault summary no more than once every 2 seconds when counters advance.
- Auto-save remains enabled, but config backup/write/file-fsync/directory-fsync work is moved to a coalescing background writer instead of blocking the Qt UI thread.
- The 25 ms safety/motion timer is retained; broad QML `stateChanged` invalidation is decimated to at most 20 Hz to reduce unnecessary UI work.
- CTRL-TS boot ID/reset reason reporting is retained, and SRVR logs a readable reset-reason label (for example SOFTWARE, PANIC, TASK_WDT or BROWNOUT) alongside the numeric value.
- macOS bundle metadata advances to short version `26.10.3`, build `2610.3.3`.

## Regression coverage

`tools/test_runtime_regression_contract.py` is now part of `tools/run_all_source_checks.py` and locks the new fixes: cumulative diagnostic baselines, persistent AUX capture, asynchronous config writes, UI signal decimation, compact state priority, independent SRVR-presence polling, completion-based POLL scheduling and consistent AUX latch timing. Existing bus-serialization, parser-diagnostic, firmware-update and safety tests remain enabled.

## Safety architecture deliberately unchanged

- W1P independent 500 ms VEL freshness watchdog.
- SRVR approximately 150 ms non-zero VEL refresh.
- AI0 E-stop / AI1 joystick mapping.
- Existing E-stop and hard-limit protections.
- Predictive stopping and dynamic soft limits.
- Leadshine velocity-control architecture.
- Approved CTRL-TS/SRVR UI design and calibration wording.

Native Arduino compilation, HMI image staging and frozen desktop builds remain GitHub Actions gates. No local firmware binary is fabricated by the source audit.
