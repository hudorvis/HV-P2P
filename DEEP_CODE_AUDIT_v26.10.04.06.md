# HV P2P v26.10.04.06 deep code audit

Date: 2026-10-04

Authoritative base: `HV P2P v26.10.04.05 - GitHub Ready Source.zip`.

## Findings and corrections

### Firmware update did not begin until CTRL / CTRL-TS reboot

CTRL already invalidated its firmware-authority match when SRVR announced a newer release, but a timing race remained at SRVR application startup: the UDP authority beacon could be received before the HTTP manifest endpoint was ready. A failed first manifest request then used the ordinary five-second retry interval. `.04.06` records a fresh mismatched SRVR session/release and enables a 15-second fast-discovery window with a 500 ms manifest retry. Once the exact image is verified, the fast window is cleared.

SRVR's asynchronous legacy update bridge remains available when an older connected CTRL reports an older firmware version through `HMI_STATUS`.

### CTRL-TS main UI lost state after firmware dashboard

`process_text_from_ctrl()` correctly refused to mutate the normal LVGL dashboard while firmware progress owned the display. The unintended consequence was that the latest `HMS1`, `HMG1` and sometimes `HMI1` model state was discarded. CTRL then cleared the associated one-shot pending flag. AUX assignment labels, ramp/Ref/preset geometry and live telemetry could therefore return stale/default after the firmware screen released.

Correction: CTRL-TS caches one latest snapshot for state, geometry and bulk live telemetry while firmware UI owns the screen. `service_fw_screen_release()` loads the main screen, applies bulk first, then the latest state and geometry overlays, explicitly redraws progress/Ref/ramp/preset markers and clears the cache.

CTRL also emits compact self-healing refreshes: state every 1000 ms and geometry every 2500 ms. These use the existing single-flight bus gate and do not alter POLL response timing or the 250 ms bulk-display cap.

### Firmware screen could remain owned indefinitely

`fw_set_device_status()` previously reset `g_fw_external_release_due_ms` on every repeated inactive firmware status packet. Since ordinary HMI packets continue to carry inactive firmware fields, the release time could be pushed forward indefinitely. `.04.06` records the row's previous active state and schedules a single two-second release only on the actual active-to-inactive transition.

### Limit Calibration layout / step count

The previous Limit wizard had a bespoke sketch and four UI steps (`Near`, `Far`, `Ref`, `Done`). The final state did not capture new data and differed unnecessarily from the approved Joystick wizard.

`.04.06` uses the same 720 x 540 visual hierarchy as Joystick Calibration with three step nodes, a Side View `SpanDiagram`, three Near/Ref/Far readout boxes, live Current Position and matching footer controls. The backend completes immediately after the Ref capture.

### Battery Change after Limit Calibration

Limit calibration completion now sets Battery Change Off, clears its outside-limit latch, marks calibration closed before resynchronising service mode, persists the result and restores the normal limit envelope. Closing calibration before the service-mode sync is important so W1P does not remain in calibration/service override after the final Ref capture.

## Preserved architecture

- W1P independent 500 ms velocity freshness watchdog.
- SRVR approximately 150 ms non-zero VEL refresh.
- AI0 E-stop / AI1 joystick mapping.
- predictive stopping/dynamic soft limits.
- Leadshine velocity architecture and hard-limit protections.
- single-flight CTRL<->CTRL-TS half-duplex scheduler.
- ACK/retry-safe touchscreen EVENT queue.
- safe display-off CTRL-TS self-flash.
- immediate CTRL-TS splash transition when SRVR exits.

Native Arduino and frozen desktop compilation remain GitHub Actions gates. Hardware timing, RS485 electrical integrity and motor motion remain bench commissioning gates.
