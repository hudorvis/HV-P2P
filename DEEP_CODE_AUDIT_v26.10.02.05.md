# HV P2P v26.10.02.05 deep code audit

## Scope

Authoritative input: v26.10.02.04 source. This audit covers the new bench reports:
headless CTRL-TS update visibility, unexpected resets after AUX confirmation,
Joystick Calibration punctuation, CTRL-TS/SRVR REF mismatch, and the SRVR status
bar diamond glyph.

## 1. CTRL-TS self-update / black screen

### Finding
The black period during CTRL-TS's own firmware write is intentional in the .04
safe updater. The safe handoff reboots into a path that does not initialize RGB,
LVGL, touch or PSRAM framebuffers before `Update.begin()` / `Update.write()`.
That boundary is retained.

The missing operator feedback was diagnostic: CTRL tracked `g_hmiFwOffset` but
`HMI_STATUS` exposed only `fw_state`, so SRVR could not show the headless transfer
percentage.

### Fix
- Added CTRL `hmiFwProgressPct()` and `fw_pct=` to `HMI_STATUS`.
- Added `safe_reboot` phase while the safe reboot quiet window is active.
- SRVR parses/exposes `ctrlTsFirmwareProgress` and Setup displays percentage for
  safe-reboot/update/verify phases.

No attempt is made to draw live progress on CTRL-TS while its own flash is being
programmed.

## 2. Unexpected CTRL-TS resets after AUX Confirm

### Audit result
No ordinary AUX action intentionally calls `ESP.restart()`. Joystick Calibration,
Drive Mode and Battery Change all travel through AUX EVENT -> CTRL -> SRVR backend
state changes. Explicit CTRL-TS restart calls are limited to firmware/recovery
paths.

A structural concurrency risk remained: `aux_event_cb()` ran in the Waveshare
LVGL task and directly called `confirm_aux_idx()`. That function mutates LVGL
objects and builds/queues dynamic Arduino `String` protocol events. Although the
pinned Waveshare port uses an LVGL mutex, putting heap/protocol/state work directly
inside the UI callback made touch processing unnecessarily re-entrant and made a
bench-only failure harder to isolate.

### Fix
- `aux_event_cb()` now only writes the AUX index into an 8-entry fixed `uint8_t`
  ring queue protected by a FreeRTOS critical section.
- `service_aux_touch_events()` runs from the Arduino main loop while the LVGL mutex
  is held and performs `confirm_aux_idx()` there.
- Removed the dormant `g_settings_reset_due_ms` touchscreen self-reset path.
- Added per-boot random `boot_id` and ESP `reset_reason` to CTRL-TS HELLO.
- CTRL relays these fields in `HMI_STATUS`; SRVR logs boot-ID changes.

This removes the identified callback-context risk but does not pretend to prove a
hardware reset cause without a reset-reason record from the physical unit.

## 3. Joystick Calibration slash punctuation

### Root cause
`Backend._display_field()` replaced both `|` and comma with `/`. Comma replacement
is needed for fields subsequently packed into comma-separated preset arrays, but
was incorrectly applied to the standalone `cal_instruction` field.

### Fix
`_display_field(..., replace_comma=False)` is used for calibration instructions.
Exact joystick prompts are:

- Hold Joystick Left, then Press Confirm
- Release Joystick to Centre, then Press Confirm
- Hold Joystick Right, then Press Confirm

## 4. REF / current-position mismatch

### Finding
Both UIs had their own local coordinate derivation. The intended formulas were
similar, but the live bench mismatch proved that independent derivation was an
unnecessary source of divergence. The packet also mixed relative display fields
with backend absolute state.

### Fix
SRVR now owns `_span_fraction(position)` and publishes `pos_frac` / `ref_frac`.
The same properties feed the SRVR Run Top/Side `SpanDiagram` and CTRL-TS travel
bar. CTRL-TS retains a legacy local-fraction fallback only if a future/older packet
omits the normalized fields.

An additional zero-position edge case was fixed by distinguishing an actual REF
value of `0.0` from `None` rather than using Python's truth-value `or` fallback.

## 5. SRVR top status diamond

### Root cause
`Main.qml` prepended `♢` or `◇` to `backend.bannerText`.

### Fix
The status Text item now renders `backend.bannerText` directly. No leading Unicode
symbol is injected.

## 6. Safety preservation review

No changes were made to:

- W1P 500 ms VEL watchdog;
- SRVR ~150 ms non-zero VEL refresh;
- CTRL AI0 E-stop / AI1 joystick channel identity;
- E-stop aggregation and firmware/link fail-safe bits;
- predictive stopping / dynamic soft limits / hard limits;
- Leadshine velocity architecture;
- CTRL-TS safe headless flash boundary or exact SHA/version/hardware gates.

## 7. Regression coverage

New/updated checks lock:

- heap-free deferred AUX callback ownership;
- no dormant ordinary UI self-reboot timer;
- CTRL-TS boot/reset telemetry end-to-end;
- CTRL-TS headless firmware percentage relay;
- exact joystick instruction punctuation;
- shared normalized REF/current fractions across SRVR and CTRL-TS;
- absence of SRVR status diamond glyph;
- all prior safe updater, RS485, OTA, Modbus, Leadshine, motion and safety contracts.

Native compilation remains authoritative in GitHub Actions. Hardware reset causality
and display behaviour require the final physical bench gate.
