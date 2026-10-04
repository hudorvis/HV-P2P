# HV P2P v26.10.04.02 change summary

Date: 2026-10-04

Authoritative lineage: `HV P2P v26.10.04.01 - GitHub Ready Source.zip` -> this `.04.02` CTRL-TS display/progress correction.

## Bench status entering this revision

The `.04.01` hardware run confirmed two important fixes: CTRL-TS AUX actions can now change Drive/Battery/Calibration state without rebooting, and closing SRVR returns CTRL-TS to the splash/waiting screen immediately. Those working paths are retained unchanged.

The remaining operator-visible issues were: incomplete/brief firmware progress presentation on CTRL-TS, `Practice Mode` clipping on the Drive Mode AUX tile, and Near/Far ramp zones that did not visually match the SRVR span diagram.

## Firmware progress dashboard

Three separate issues were corrected without weakening the safe headless CTRL-TS updater:

- CTRL's own authority OTA progress callback used the normal HMI sender after CTRL deliberately marked normal HMI compatibility false. That could suppress real CTRL `FWSTAT` percentages exactly while CTRL was updating. `.04.02` adds a firmware-status sender that bypasses only the normal compatibility gate while retaining the same single-flight RS485 protections: no transmission during CTRL-TS firmware transfer, no transmission while a POLL/EVENT transaction is outstanding, and no transmission during bus-recovery quiet time.
- Compact `HMS1` state now carries CTRL and W1P firmware active/phase/percentage fields so the three-row CTRL-TS dashboard is not dependent on the slower bulk HMI frame.
- CTRL-TS self-update is deferred while SRVR reports CTRL or W1P still updating. CTRL-TS therefore stays alive as the operator display for those two nodes and enters its own updater last.

Immediately before its own safe reboot, CTRL-TS now shows `Preparing safe updater` for approximately 900 ms. The actual CTRL-TS flash write remains intentionally headless/display-off. During that final phase the physical CTRL-TS is black and SRVR remains the authoritative exact percentage display. This preserves the proven ESP32-S3 RGB/PSRAM-safe updater rather than reintroducing live-display flash programming.

## Drive Mode AUX text

The AUX value row now uses almost the full tile width, a 10 px Montserrat font and explicit single-line clipping. `Practice Mode` therefore fits within the approved tile geometry instead of wrapping/cropping to `Practice Mo`.

No tile dimensions or approved overall CTRL-TS layout were changed.

## Near/Far ramp display

The old CTRL-TS implementation drew each ramp zone as a thin constant-height rectangle. SRVR's `SpanDiagram` represents the Near/Far ramp regions as wedges that grow from each hard-limit endpoint toward the configured ramp boundary.

`.04.02` changes CTRL-TS to the same proportional wedge semantics using ten lightweight 1-pixel strips per side. Ramp widths remain based on `ramp_near / (far-near)` and `ramp_far / (far-near)`, and the ramp fields are now also included in compact `HMS1` state so Settings changes converge promptly without waiting for bulk telemetry.

## Preserved architecture

The `.04.01` AUX null-pointer fix, ACK/retry event queue, immediate SRVR-offline splash behavior, 60 ms normal HMI polling, 250 ms POLL response timeout, 300 ms recovery quiet period, 4 Hz bulk HMI cap, W1P setting convergence, 500 ms W1P velocity watchdog, ~150 ms SRVR non-zero VEL refresh, AI0/AI1 mapping, E-stop/hard-limit protections, predictive stopping/dynamic soft limits and Leadshine velocity architecture are retained.

The approved SRVR QML/UI is unchanged in this revision.
