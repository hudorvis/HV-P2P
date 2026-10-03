# HV P2P v26.10.03.05 — whole-project communications audit

Date: 2026-10-03

Authoritative base: `HV P2P v26.10.03.04 - GitHub Ready Source.zip`.

## Scope

This audit traced operator input and state end-to-end across SRVR, CTRL, CTRL-TS and W1P, including UDP receive/transmit queues, CTRL A7 flags, CTRL↔CTRL-TS framed RS485, AUX acknowledgement/deduplication, persistent settings, joystick calibration, graceful/abnormal disconnect safety, firmware progress and UI-thread work.

## CTRL ↔ CTRL-TS

The `.03.01-.03.04` single-flight scheduler is structurally sound: one POLL can be outstanding, normal TEXT is blocked while waiting for EVENT, stale sequence responses are rejected, timed-out transactions enter a master-silent recovery window, firmware owns the bus exclusively, and touchscreen events are retained until explicit ACK.

Two remaining timing inefficiencies were found. First, CTRL-TS's normal `handle_hmi_rx()` ran while the Arduino loop held the LVGL mutex, allowing display work to delay a POLL response. Second, after CTRL transmitted a large TEXT frame, its old poll timestamp could already be expired, causing a POLL immediately after the frame even though CTRL-TS had only just begun applying it. `.03.05` services RS485 before the main LVGL critical section and restarts the poll interval after a completed normal TEXT transmission.

The 60 ms normal POLL interval is intentionally not made shorter: average no-load event pickup remains about 30 ms, while the 250 ms response timeout and 300 ms recovery quiet window provide much larger real-hardware scheduling margin. Bulk display forwarding remains 250 ms/4 Hz. Idle EVENT diagnostics are compressed and full diagnostics are sent on events/once per second.

## SRVR ↔ CTRL

CTRL control input remains 25 ms. AI0 physical E-stop and AI1 joystick mapping are unchanged. AUX1..AUX5 touchscreen events are converted by CTRL into 300 ms A7 flag latches; SRVR's UDP listener edge-captures those flags independently of the Qt timer, together with the exact joystick value in the same datagram. This makes AUX execution and joystick calibration resilient to desktop repaint stalls.

SRVR display state is repeated latest-state UDP and self-healing. Critical state fields (Drive Mode, Acceleration Mode, Battery Change, service/calibration/AUX labels and core link/safety state) are extracted by CTRL into HMS1 priority updates so they do not need to wait for a bulk HMI1 frame.

## SRVR ↔ W1P

The main defect was settings semantics rather than raw link speed. Persistent settings were sent as a burst of one-shot UDP `SET_*` commands. W1P STATUS already reported the values, but SRVR used several reported values to overwrite its desired configuration. A lost SET could therefore cause an operator selection to appear to revert instead of being retried.

`.03.05` separates **desired** and **reported** configuration. SRVR remains authoritative, W1P STATUS is confirmation, and mismatches stay pending until confirmed. At most one persistent setting command is emitted at a time, with >=40 ms spacing and a 350 ms per-key retry interval. This deliberately avoids competing with VEL/STOP traffic. W1P still streams STATUS every 50 ms; SRVR's explicit STATUS probe is only 250 ms.

The W1P receive filter also omitted `FW_PROGRESS` even though the downstream parser supported it. That filter is corrected.

## Servo Enable / safety ownership

W1P previously cleared `software_srvon_inhibit` automatically when its physical E-stop cleared and when SRVR connectivity returned. That conflicted with SRVR's neutral-return re-arm contract. `.03.05` leaves the inhibit latched through both events. The only normal clear is the explicit `SW_SRVON 1` command after W1P safety latches are clear and SRVR has satisfied the neutral requirement.

This does not alter the independent 500 ms W1P VEL watchdog. Graceful SRVR shutdown still directly repeats `STOP` + `SW_SRVON 0`; abnormal loss remains independently protected by W1P command freshness and CTRL/SRVR peer timeouts.

## SRVR desktop responsiveness

Auto-save remains asynchronous. Config notification is now deferred/coalesced with `QTimer.singleShot(0, ...)` so a ComboBox activation can finish before dependent QML bindings are refreshed. Bulk DSP1 construction is limited to the same 100 ms cadence as changed display transmission. Existing hidden-page/log/profile optimizations remain.

## User inputs/settings

The QML/backend interface audit found no missing slot/property: all referenced backend actions resolve. Desktop and touchscreen Drive Mode/Acceleration Mode/Battery Change use common setters. AUX calibration actions advance the already-open wizard rather than reopening it. Joystick calibration uses event-time samples. Settings/Free-D remain auto-save with no Apply/Reset controls.

## Remaining bench evidence required

No normal AUX path intentionally calls `ESP.restart()` on CTRL-TS. If the touchscreen still genuinely resets after Confirm, use SRVR's boot-id/reset-reason and pre-reset heap/min-heap/PSRAM diagnostics to classify the reset. Source audit cannot truthfully distinguish panic/task-WDT/brownout without that hardware result.

Native firmware and frozen macOS/Windows compilation are intentionally left to GitHub Actions. Physical RS485 electrical integrity, Waveshare reset cause and powered Leadshine behavior remain commissioning gates.
