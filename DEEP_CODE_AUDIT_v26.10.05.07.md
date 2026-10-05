# HV P2P v26.10.05.07 deep code audit

Date: 2026-10-05

Authoritative starting source: `HV P2P v26.10.05.06 - GitHub Ready Source.zip`.

## Audit scope

The `.05.06` source was re-audited end-to-end for the reported bench issues: CTRL-TS final OTA reboot, touchscreen travel-layout overlap, Settings wording, calibration placeholder/Cancel behavior, transient red/E-stop state during Limit Calibration, macOS background connectivity, and random stops while travelling to the Far calibration point. Existing W1P watchdog, Leadshine velocity, AI0/AI1, hard-limit/predictive-limit, RS485 single-flight and firmware-ordering contracts were treated as locked safety behavior.

## Root causes and fixes

### 1. CTRL-TS remained black after a successful self-update

`.05.06` correctly verified the transferred image, called `Update.end(true)` and persisted the target identity. The coordinator defect was after that point: CTRL treated a `REBOOT` ACK from the still-running updater as completion and immediately reset its firmware transaction. That ACK proves only receipt of the command; it does not prove the ESP32 restarted or that the selected image booted.

`.05.07` adds a post-ACK confirmation phase. CTRL records the pre-update CTRL-TS `boot_id`, continues bounded reboot enforcement/discovery, and completes only when a later `HELLO_RESP` proves a different `boot_id` plus the exact required target version and SHA-256. A reboot into the wrong image is not accepted as success. CTRL-TS also retains the autonomous verified-image reboot fallback in its headless loop.

### 2. Near/Far values overlapped preset names

The overlap was deterministic geometry: the 91 px travel panel placed Near/Far values in the same vertical band used by the upper preset-name lane. The fix reclaims height from the AUX row, makes the travel panel 100 px high, and separates endpoint/readout, track/marker/ramp and preset-label lanes. No font is reduced below Montserrat 10.

### 3. Settings -> CTRL-TS used `CTRL-TS Link`

The QML contained a stale literal while CTRL and W1P already used `Link`. The validator also explicitly expected the stale text. Both source and validation contract now require `Link`.

### 4. Calibration unknown glyph and missing Cancel

The CTRL-TS overlay substituted Unicode em dash for an empty capture. That glyph is absent from the compiled LVGL Montserrat font and rendered as the replacement rectangle. The touchscreen now uses ASCII `-` for uncaptured Joystick Left/Centre/Right and Limit Near/Ref/Far values.

There was also no touchscreen calibration-cancel protocol. `.05.07` adds a dedicated Cancel button and routes `CAL_CANCEL` through the existing acknowledged/retried HMI EVENT mechanism. CTRL translates it to a dedicated A7 flag and SRVR edge-captures it so an event is not lost if the GUI timer is delayed.

A deeper issue was found in Limit Calibration: `.05.06` was not transactional. Near/Far captures could mutate live calibration before Ref completion, and Far could change/save `reverse_motor` before the wizard finished. `.05.07` stages Near/Far/Ref/raw captures and the proposed Winch Invert value. The complete calibration is committed only at final Ref confirmation. Cancel therefore cannot partially overwrite the previous calibration.

### 5. Brief red state during Limit Calibration

The touchscreen's own 30 s HMI timeout does not paint the authoritative System banner red, so masking that timer would have hidden the wrong problem. The actual source-level false-fault path was in SRVR W1P status arbitration: `.05.06` invalidated the previous W1P snapshot before proving that the new `STATUS` frame was complete and parseable. One malformed/incomplete frame could therefore create a short fail-safe state; the next valid status restored it, producing a brief red flash. `PONG` also unnecessarily invalidated status authority.

`.05.07` validates mandatory status fields, strict 0/1 safety tokens, RS485/config enums and finite numeric fields first, then commits the new snapshot. A rejected sample leaves the previous complete sample authoritative only until the existing freshness timeout expires. Real stale/fault conditions still go red. `PONG` is liveness-only. Rejected frames are counted and rate-limited in the log for bench diagnosis.

The source does not prove why a malformed packet appeared at an approximately 30 s bench cadence; claiming a specific electrical/packet corruption source without a captured bench log would be speculative. The faulty arbitration that converted one bad sample into an immediate red state is nevertheless removed.

### 6. CTRL-TS red connection flash when SRVR is backgrounded on macOS

CTRL's SRVR peer timeout is 750 ms. `.05.06` relied on Qt-timer-owned SRVR traffic closely enough to that timeout that background scheduling/App Nap pressure could consume the available margin. The HMI then correctly saw CTRL report SRVR offline and entered its red/offline presentation even though the process was still running.

`.05.07` adds a lightweight `SRVR_ALIVE` packet emitted by a dedicated communications worker every 250 ms. CTRL accepts this packet only as process/transport liveness; it carries no motion or safety authority. Graceful shutdown stops the worker and sends `SRVR_OFFLINE` under the same TX lock, preserving the immediate Waiting/Splash behavior.

### 7. Skate stopped randomly while moving toward the Far Limit

The required joystick-to-neutral action is caused by the intentional post-safety neutral interlock. Any safety interruption sends STOP and prevents automatic restart until the operator deliberately passes the joystick through neutral. That interlock must remain.

During calibration, normal soft limits are already bypassed by service mode, so random mid-span stops were not caused by the saved Near/Far envelope. The false transient W1P-status invalidation above could trip the safety stop/interlock. In addition, normal non-zero VEL refresh was produced by the Qt control tick; a sufficiently delayed GUI tick could approach W1P's 500 ms independent freshness watchdog.

`.05.07` removes the false STATUS invalidation and gives the W1P communications worker a short-lived copy of the current non-zero VEL command. Normal transmission remains ~150 ms. If one Qt interval is missed, the worker may bridge it at 180 ms; the lease expires unless the control loop keeps renewing it, so a genuinely stalled SRVR still loses VEL freshness and W1P's unchanged 500 ms watchdog stops the drive.

## Preserved safety/control architecture

- W1P independent `W1P_VEL_COMMAND_TIMEOUT_MS = 500` remains unchanged.
- Normal SRVR non-zero VEL refresh remains approximately 150 ms.
- AI0 E-stop / AI1 joystick mapping is unchanged.
- Post-fault joystick-neutral re-arm is unchanged.
- W1P service-mode reduced-speed calibration behavior is retained.
- Predictive stopping/dynamic soft limits and W1P hard-limit protections are retained.
- Leadshine Modbus RTU velocity architecture is retained.
- CTRL <-> CTRL-TS half-duplex single-flight scheduling and EVENT ACK/retry semantics are retained.
- Firmware update ordering remains CTRL -> W1P -> CTRL-TS.
- CTRL-TS remains headless/black while actually writing its own flash.

## Verification status

The complete local source/static/regression/preflight suite passes. `test_bench_regression_0507.py` locks the new reboot-confirmation, layout, Cancel, transactional calibration, validate-before-commit status and background-liveness contracts. The PySide backend runtime regression is retained for GitHub Actions where PySide6 is installed. Native ESP32 and frozen desktop compilation remain GitHub Actions authoritative; no local firmware binaries are release artifacts.
