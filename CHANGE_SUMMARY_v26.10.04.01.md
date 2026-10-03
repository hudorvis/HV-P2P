# HV P2P v26.10.04.01 change summary

Date: 2026-10-04

Authoritative lineage: `HV P2P v26.10.03.05 - GitHub Ready Source.zip` -> this `.04.01` bench-crash correction.

## Why this revision exists

The `.03.05` bench run confirmed that the SRVR responsiveness and Joystick Calibration changes were effective, but every CTRL-TS AUX confirmation still ended in a genuine touchscreen reset roughly when the two-second Confirmed indication expired. Drive Mode reached SRVR before the reset, Battery Change did not on that run, and completing Joystick Calibration also produced the same text/garbage flash followed by reboot.

## Exact CTRL-TS reboot root cause

The production CTRL-TS UI intentionally removes the service/debug label by setting `lbl_touch_debug=nullptr`. The AUX confirmation timeout path in `service_link_state()` nevertheless still called `lv_label_set_text(lbl_touch_debug,"Ready")` directly after the two-second Confirmed latch expired.

That is a direct LVGL call with a null object pointer. It sits on the exact common path used after Drive Mode, Battery Change and calibration AUX confirmations, and explains the characteristic screen corruption/text flash immediately before the ESP32 restarts.

`.04.01` removes the direct dereference and routes the transition through the existing null-safe `set_touch_debug()` / `set_label_text_if_changed()` helper. A regression test now fails if the production UI has `lbl_touch_debug=nullptr` while any direct `lv_label_set_text(lbl_touch_debug, ...)` call exists.

## AUX delivery hardening

- `send_hmi_command()` now returns success/failure.
- A tile is not allowed to remain visually Confirmed if its command could not enter the retry-safe CTRL-TS EVENT queue.
- If the fixed event queue is full, the tile remains selected at Confirm? so the operator can deliberately retry instead of being shown a false success.
- Existing EVENT ID / explicit ACK / retry / duplicate-suppression behavior is retained.
- CTRL now reports the last accepted event ID and compact AUX command in `HMI_STATUS`.
- SRVR logs the accepted CTRL-TS event and logs the resulting Drive/Battery/Acceleration state after applying an AUX action. This gives the next bench run a direct trace for the Battery Change report without increasing normal UI traffic materially.

## Battery Change finding

The project-wide source trace does **not** show an AUX4 16-bit wire-format defect. CTRL transmits A7 flags as high-byte + low-byte, SRVR parses the complete 16-bit field, and AUX4/AUX5 use the same listener-thread edge capture as AUX1-AUX3. The `.03.05` Battery miss therefore cannot honestly be attributed to truncation from the source alone.

With the common post-confirm crash removed, `.04.01` keeps the existing reliable event pipeline and adds enough end-to-end logging to distinguish: touchscreen event not queued, event not accepted by CTRL, AUX edge not processed by SRVR, or Battery state applied and then changed elsewhere.

## Firmware-update display behavior

CTRL-TS self-programming remains intentionally headless: after the safe reboot, RGB/LVGL are not started and the physical panel remains black while SRVR shows the transfer percentage. The normal runtime no longer draws a CTRL-TS self-update page before this handoff. A brief update dashboard may still legitimately appear if CTRL or W1P itself is reporting `FWSTAT` progress immediately before the CTRL-TS update begins.

## Preserved architecture

The `.03.05` communications audit remains intact: single-flight CTRL↔CTRL-TS half-duplex scheduling, 60 ms normal POLL cadence, 250 ms response timeout, 300 ms recovery quiet period, 4 Hz bulk HMI ceiling, compact priority HMS1 state, STATUS-confirmed W1P setting convergence, neutral-verified Servo-Enable re-arm, 500 ms W1P VEL watchdog, ~150 ms SRVR non-zero VEL refresh, AI0/AI1 mapping, hard limits, predictive stopping/dynamic soft limits and Leadshine velocity architecture.

The approved SRVR QML/UI is unchanged.
