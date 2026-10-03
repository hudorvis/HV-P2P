# HV P2P v26.10.04.01 — CTRL-TS post-confirm crash audit

Date: 2026-10-04

Authoritative base: `HV P2P v26.10.03.05 - GitHub Ready Source.zip`.

## Bench evidence reviewed

- SRVR is substantially more responsive.
- CTRL-TS Drive Mode command reaches SRVR, then CTRL-TS reboots.
- CTRL-TS Battery Change command did not change SRVR on the observed attempt, then CTRL-TS reboots.
- Joystick Calibration works correctly on both displays, including event-time joystick capture, but the final CTRL-TS confirmation again flashes text/lines and reboots.
- During CTRL-TS self-update, the screen becomes black while SRVR continues to report update progress.

## Exact common reboot path

The approved production face contains no service/debug label:

`lbl_touch_debug = nullptr`.

Most debug writes already use `set_touch_debug()`, which calls a null-safe helper. One stale direct LVGL write remained in `service_link_state()`:

`lv_label_set_text(lbl_touch_debug, "Ready")`.

That statement runs when `confirmed_aux` expires, two seconds after a confirmed AUX press. It therefore executes after Drive Mode, Battery Change and the AUX press that completes/advances a calibration wizard. Passing the null production pointer into LVGL is an invalid object access and is the source-level root cause matching the common panic/reboot timing and corrupted/text-line frame immediately before reset.

`.04.01` replaces the direct write with the null-safe helper and adds a source regression that locks this invariant.

## AUX queue semantics

CTRL-TS continues to queue fixed-size `AUX1`...`AUX5` EVENTs. Events remain queued until CTRL sends an explicit ACK for their event ID, so a lost/corrupt EVENT or ACK is retried safely. `.04.01` additionally prevents a local false-confirm state if the event queue itself is full: the tile stays at Confirm? for another deliberate press.

CTRL still converts an accepted touchscreen EVENT to the corresponding 300 ms A7 AUX flag. CTRL emits control packets every 25 ms, so a normal accepted event is represented in multiple packets. SRVR's UDP receiver thread captures the rising edge independently of Qt rendering and preserves the joystick sample from that same packet.

## Battery Change path

A source-level check of AUX4 found:

- CTRL `FLAG_AUX4 = 0x0100`.
- A7 wire format sends `(flags >> 8)` then `(flags & 0xFF)`.
- SRVR reconstructs `(data[1] << 8) | data[2]`.
- `CTRL_AUX_BITS` includes AUX4 and AUX5.
- The listener-thread event queue handles all five AUX bits with the same rising-edge logic.
- `_handle_aux_action()` maps the same configured assignment used to generate the visible AUX tile label.

Therefore the reported one-off Battery miss is not explained by an obvious high-byte truncation or label/action index mismatch in `.03.05`. `.04.01` adds low-rate diagnostics: CTRL reports `last_event_id` / `last_event_cmd`, SRVR logs that accepted command, and the SRVR AUX log records the resulting Drive/Battery/Acceleration state. This permits the next physical run to locate any remaining Battery-specific failure precisely.

## Firmware screen

CTRL-TS self-flash is intentionally black. The safe updater stages the target, switches the panel backlight/reset low and software-reboots into a headless boot where RGB/LVGL/PSRAM display resources are not initialized. SRVR remains the progress surface.

The normal runtime does not intentionally render a CTRL-TS self-update dashboard immediately before that safe reboot. The same touchscreen may however briefly show the firmware dashboard for a preceding CTRL or W1P `FWSTAT` update. This is independent of the AUX panic.

## Timing/safety retained

No RS485 timing constants are loosened or accelerated in this revision. The `.03.05` values remain the selected balance for hardware margin: 60 ms polling, 250 ms POLL response timeout, 300 ms post-timeout quiet period and 250 ms/4 Hz bulk display forwarding. Firmware transfer remains exclusive.

W1P's independent 500 ms velocity watchdog, SRVR ~150 ms non-zero VEL refresh, STOP/SW_SRVON shutdown path, physical E-stop handling, hard limits, predictive stopping/dynamic soft limits and Leadshine velocity architecture are unchanged.

## Verification boundary

Source/regression/preflight checks are run locally. GitHub Actions/native Arduino compilation and frozen desktop builds remain authoritative. The next bench run should verify that the common post-confirm reboot is gone; if Battery Change alone still fails, the new event/result log lines identify exactly which boundary failed.
