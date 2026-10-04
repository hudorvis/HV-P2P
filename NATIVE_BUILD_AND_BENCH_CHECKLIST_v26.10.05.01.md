# HV P2P v26.10.05.01 Native Build and Bench Checklist

## Release gate order

1. Require `ALL_SOURCE_CHECKS_PASS` from the repository source suite.
2. Run GitHub Actions native firmware/desktop jobs; GitHub/native compilation is authoritative.
3. Use only matching `.05.01` STAGED_SOURCE / firmware / desktop artifacts.
4. Bench-test CTRL/CTRL-TS/W1P with the winch unable to move.
5. Only after display/update/safety gates pass, continue to unloaded then loaded motion commissioning.

## 1. Automatic firmware convergence and update order — highest priority

Start with compatible `v26.10.04.07` CTRL, W1P and CTRL-TS already running. Then launch the newer `.05.01` SRVR. Do **not** manually reboot any ESP32.

Expected order/behavior:

- CTRL detects SRVR authority and begins its update without a manual reboot.
- Before CTRL's blocking download begins, the CTRL↔CTRL-TS normal transaction must quiesce; no outstanding POLL may remain.
- SRVR CTRL Firmware field must show CTRL update phase/percentage.
- CTRL-TS must show CTRL firmware progress while its normal display is available.
- W1P authority/update is advertised only after CTRL is current/fresh. If W1P is connected and old, verify W1P then updates and its phase/percentage appears on SRVR and CTRL-TS.
- CTRL-TS self-update permission must remain false until CTRL is current and W1P has either converged or the no-W1P discovery window has elapsed.
- Immediately before its own safe reboot, CTRL-TS should show `Preparing safe updater - SRVR shows self-flash progress`.
- During CTRL-TS **own actual flash**, the panel is intentionally black. SRVR must continue showing the exact CTRL-TS percentage. Do not reject the release because of this intentional headless phase.
- After verified CTRL-TS reboot, the normal UI must repopulate promptly with current status, AUX assignments, position/speed, geometry, REF and presets.

Reject the release if CTRL/W1P/CTRL-TS start in the wrong order, if a manual reboot is required to begin a modern authority update, or if CTRL progress is absent while CTRL is actually downloading/staging.

## 2. Canonical status alignment

Verify SRVR and CTRL-TS show the same status at the same time and with identical wording/colour:

- green: `System | Active`
- yellow: `System | Uncalibrated`
- yellow: `System | Battery Change Mode`
- yellow: `System | Joystick Calibration`
- yellow: `System | Limit Calibration`
- yellow: `System | Winch Calibration`
- red: `E-Stop | SRVR`, `E-Stop | CTRL`, `E-Stop | W1P`, or combined sources as appropriate

Specific regression:

- Start an uncalibrated session and leave it untouched for at least 60 seconds while position/geometry packets are flowing. CTRL-TS must stay solid `System | Uncalibrated`; it must not flash to Active.
- Enter Battery Change Mode from both SRVR and CTRL-TS. Both displays must become yellow `System | Battery Change Mode`.
- Complete/exit service modes and verify both surfaces converge to the same next state.

## 3. CTRL-TS live motion cadence/readability

With a safe simulated or unloaded motion test:

- SRVR and CTRL-TS Current Position, Speed, To Near, To Far and the skate marker must all move in the same direction and represent the same values.
- CTRL-TS movement should visually refresh around 10 Hz, not only 2–4 times per second.
- The marker may interpolate only between received verified samples; it must not run ahead of received data.
- Monitor RS485 counters while moving. POLL timeout/CRC/resync counters should remain stable under normal wiring.
- Confirm the ~900-byte bulk HMI still remains at 4 Hz maximum.

Typography:

- Preset labels and Near/Far/distance small text must be no smaller than the small `Drive Mode` / `Acceleration Mode` text (Montserrat 10).
- Reject unreadable 8 px preset/position labels.

## 4. Geometry / REF / presets

Set a known Near/Far span, non-zero Near/Far ramp zones, REF, and several visible presets.

Compare SRVR Side View and CTRL-TS:

- Near and Far boundaries align.
- Near/Far ramp wedge boundaries align.
- Current skate position aligns at the same normalized fraction.
- REF aligns at the same normalized fraction.
- Every visible preset aligns at the same normalized fraction and has readable text.
- Signed To Near / To Far values remain correct during Battery Change excursions outside the saved span.

Change geometry while connected and verify the CTRL-TS converges without requiring an unrelated settings change or reboot.

## 5. Limit Calibration wizard layout/function

The SRVR Limit Calibration wizard must deliberately match the approved Joystick Calibration wizard shell:

- same 720×540 modal style;
- same three-step header structure;
- exactly three steps: `Set Near` → `Set Far` → `Set Ref & Done`;
- one central cable-position visual;
- three Near / Ref / Far value boxes;
- live Current Position while the wizard is open.

Visual acceptance:

- both tower icons must be fully visible from top to bottom;
- cable must remain inside the central viewport;
- cable must not be clipped or unnaturally forced from extreme bottom-left to extreme top-right;
- Near/Ref/Far capture markers and values must remain visible as steps advance.

Functional acceptance:

- With Position Source = Virtual and W1P disconnected, use the joystick to move the simulated skate; Current Position and the cable marker must change live.
- Capture distinct Near, Far and Ref values.
- The third Ref confirmation must close the wizard immediately; no fourth Done step exists.
- A duplicate/late confirmation after close must not recapture Ref.
- Completing Limit Calibration must force Battery Change Mode Off.

## 6. AUX assignment/state regression

Configure, for example:

- AUX3 = Joystick Calibration
- AUX4 = Limit Calibration
- AUX5 = Ref Point Slip

Reboot/reconnect CTRL and CTRL-TS and pass through a firmware dashboard if practical.

- CTRL-TS must show the live SRVR assignments, not legacy `Accel Type / Goto Ref / AUX 5` labels or generic Aux 1..5 names.
- Each first press selects/asks Confirm; each second press queues exactly one EVENT.
- Confirmed actions must not reboot CTRL-TS.
- SRVR must execute each accepted action once; no lost or double-executed event.

## 7. Joystick calibration/readout

Prompts remain exactly:

- `Hold Joystick Left, then Press Confirm`
- `Release Joystick to Centre, then Press Confirm`
- `Hold Joystick Right, then Press Confirm`

After completion:

- operator Percentage at a healthy neutral within deadband should display `0.0%`;
- Left/Right should approach -100/+100% as calibrated;
- the stored raw calibration/motion math must not be altered merely to cosmetically force 0.0 outside deadband.

## 8. Battery Change Mode

Verify:

- mode is yellow `System | Battery Change Mode` on SRVR and CTRL-TS;
- commanded speed is restricted to the commissioned service cap;
- software Near/Far ramp/predictive envelope may be crossed deliberately for battery servicing;
- independent E-stop/link/watchdog protections remain active;
- outside Near: To Near becomes negative and To Far increases beyond span;
- outside Far: To Far becomes negative and To Near increases beyond span;
- after a genuine outside excursion, returning inside the safe span automatically disables Battery Change;
- completing Limit Calibration also forces Battery Change Off.

## 9. SRVR shutdown / fail-safe

On normal SRVR exit:

- CTRL-TS should move to Waiting/Splash essentially immediately;
- SRVR sends urgent repeated `STOP` + `SW_SRVON 0` before teardown;
- W1P should be stopped/inhibited and the commissioned brake behavior should apply.

For abnormal SRVR loss, preserve the independent W1P 500 ms VEL freshness watchdog as the motion fallback.

## 10. Safety/watchdog invariants

Confirm no regression to:

- W1P independent VEL freshness watchdog = 500 ms;
- SRVR non-zero VEL refresh ≈ 150 ms;
- CTRL AI0 physical E-stop / AI1 joystick mapping;
- W1P DI0 E-stop;
- hard limits;
- predictive/dynamic soft limits;
- Leadshine closed-loop velocity architecture;
- software Servo Enable remains inhibited until SRVR's explicit neutral-verified re-arm.

## 11. Acceptance archive

Archive:

- successful GitHub Actions native firmware and desktop logs;
- Complete Release/checksum manifests;
- SRVR/CTRL/CTRL-TS logs for a no-manual-reboot `.04.07` → `.05.01` update;
- video/screenshots of aligned canonical statuses;
- smooth CTRL-TS live marker/geometry test;
- Limit Calibration wizard visual/function test;
- E-stop/watchdog/limit commissioning records before loaded motion acceptance.
