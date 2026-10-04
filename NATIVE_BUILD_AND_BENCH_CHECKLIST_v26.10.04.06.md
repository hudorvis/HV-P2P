# HV P2P v26.10.04.06 Native Build and Bench Checklist

## Release gate order

1. Require `ALL_SOURCE_CHECKS_PASS` from the repository source suite.
2. Run GitHub Actions native firmware/desktop jobs; do not substitute fabricated
   local binaries for release artifacts.
3. Use only the matching Complete Release / STAGED_SOURCE / firmware artifacts.
4. Bench-test CTRL/CTRL-TS/W1P with the winch unable to move.
5. Only after display/update/safety gates pass, continue to unloaded then loaded
   motion commissioning.


## v26.10.04.06 communications/settings gates

- Change Drive Mode, Acceleration Mode and Battery Change Mode repeatedly from SRVR. Each selection should close without a 1–2 s UI stall and CTRL-TS should converge to the selected state promptly.
- Repeat the same actions from CTRL-TS. Verify SRVR changes exactly once per confirmed press; no accepted command may be silently lost or executed twice.
- Change W1P Units/m, Winch Invert, acceleration profile values and calibrated limits with one setting at a time. Verify W1P STATUS converges to each SRVR value and the SRVR value does not revert if a SET datagram is deliberately dropped.
- Confirm W1P firmware update progress reaches SRVR (`FW_PROGRESS`) during an authority update.
- Confirm physical E-stop clear and SRVR reconnect leave software Servo Enable inhibited until the joystick-neutral re-arm completes and SRVR explicitly sends `SW_SRVON 1`.
- Exercise CTRL-TS while bulk position telemetry is changing. AUX response should remain prompt; RS485 poll timeout/CRC/resync counters should remain stable under normal wiring.

## CTRL-TS boot and AUX stability — highest-priority .03.05 bench gate

- Power-cycle CTRL-TS at least 10 times. Every boot must reach a correctly scaled
  800x480 splash/main UI with no colour cycling, repeated rows or displaced bands.
- Repeat **each AUX tile** first-select + second-confirm at least 20 times.
- Specifically test AUX assignments for:
  - Joystick Calibration;
  - Limit Calibration;
  - Winch Calibration;
  - Drive Mode;
  - Battery Change Mode;
  - Acceleration Mode.
- No ordinary AUX action is permitted to restart CTRL-TS.
- If a restart occurs, preserve SRVR/CTRL logs. `.03.05` must report a changed
  CTRL-TS `boot_id`, readable `reset_reason`, and the last reported touchscreen
  free-heap/min-heap/free-PSRAM values so the reset can be classified from evidence
  rather than assumed.
- Confirm runtime SRVR loss returns to the resident `Waiting for SRVR` splash and
  link recovery restores the main UI without an ESP restart.


## SRVR Intel macOS responsiveness

- Open each Settings/Free-D ComboBox repeatedly (especially Battery Change,
  Acceleration Mode and Drive Mode). Selecting an item should close the dropdown
  promptly; reject the previous 1–2 second UI-thread stall.
- Leave SRVR connected to CTRL/CTRL-TS for at least 10 minutes after deliberately
  creating one RS485 timeout/error counter. The log must not repeat the same
  cumulative counter every 250 ms and the Log page must remain responsive.
- Change several auto-save Settings/Free-D values rapidly. UI interaction must
  remain responsive while the background config writer persists the latest state.
- Toggle Battery Change and Drive Mode from SRVR repeatedly and confirm CTRL-TS
  reflects each change promptly through the compact priority state path.
- Quit SRVR normally with motion physically prevented. Verify SRVR sends the
  urgent W1P STOP + software Servo Enable inhibit before teardown, and CTRL-TS
  returns to `Waiting for SRVR` on the next practical POLL opportunity rather than
  waiting ~5 seconds. Confirm W1P reports stopped/inhibited and the commissioned
  BRK-OFF output reaches the braked state.

## Joystick Calibration wizard

- Assign `Joystick Calibration` to an AUX tile.
- Prompts must read exactly:
  - **Hold Joystick Left, then Press Confirm**
  - **Release Joystick to Centre, then Press Confirm**
  - **Hold Joystick Right, then Press Confirm**
- There must be no lower `Use the assigned AUX...` description row.
- Each confirmed step must advance exactly once and clear the previous Confirmed
  latch so the next step is immediately available.
- Deliberately create moderate SRVR UI activity, then hold Left/Centre/Right and
  Confirm from CTRL-TS. The captured value must correspond to the joystick position
  **at the Confirm event**, not wherever the stick is when SRVR later repaints.
- The wizard must remain scaled correctly and must not reboot CTRL-TS.
- After completion, SRVR joystick Value/Percentage must use the calibrated range.

## CTRL-TS self-update — intentional black headless phase

The physical CTRL-TS display is intentionally **off** while CTRL-TS programs its
own flash. This is the safe design; RGB/LVGL/PSRAM are not initialized in the
headless updater.

1. Start a controlled automatic CTRL-TS update from a matched `.04+` safe-OTA
   baseline.
2. The touchscreen should remain available for CTRL/W1P progress. Immediately before
   its own deliberate safe reboot it should show `Preparing safe updater - SRVR shows
   self-flash progress` for about 1.8 s.
3. It must then deliberately go dark. There must be no green/blue/white/black
   cycling, duplicated rows or partial UI during flash programming.
4. While the physical screen is dark, open SRVR Setup and verify the CTRL-TS
   Update row shows the headless phase and increasing percentage.
5. CTRL serial should show FW block progress and exact size/SHA verification.
6. After verified reboot, CTRL-TS must return to the correctly scaled normal UI
   and report matching version/SHA.
7. If no transfer starts after safe reboot, the 60 s recovery guard must return
   the unit to the normal application rather than leave it black forever.

**Manual Arduino flash note:** a manual CTRL-TS flash has no trusted staged-image
SHA metadata. If CTRL carries the exact GitHub release image it may immediately
perform one same-version exact-image synchronization. That is expected. Monitor
its percentage in SRVR and allow it to finish.

## W1P / CTRL firmware progress

- While CTRL-TS is in normal UI mode, controlled W1P and CTRL updates should show
  their phase/percentage on the touchscreen firmware dashboard.
- CTRL-TS's own update percentage is viewed in SRVR while the panel is off.
- A firmware update must never unblock motion safety merely because its progress
  display is active.

## Canonical position / REF display consistency

- Set a known Near/Far span and a REF point at several locations, including about
  5%, 50% and 95% of span.
- Compare the CTRL-TS travel bar with SRVR Run Top View and Side View.
- REF must occupy the same horizontal fraction on all three displays.
- Repeat for current position/skate marker.
- Include a valid reference of exactly `0.0` where the configured span permits it,
  verifying that `0.0` is not mistaken for an unset (`None`) reference.

## SRVR status bar

- Confirm red status appears as plain text such as **E-Stop | W1P** or
  **E-Stop | CTRL & W1P** with no leading diamond/unknown character.
- Confirm yellow `System | Uncalibrated` and green `System Ready` also contain no
  decorative unknown glyph.

## Automatic SRVR release convergence

- Launch a newer SRVR with compatible older CTRL/W1P nodes running; do not reboot
  the nodes first.
- Confirm release mismatch is detected through lightweight UDP authority beacons,
  then the nodes enter the fail-closed update path.
- Leave a matched CTRL running for several minutes: there must be no periodic
  blocking HTTP authority polling in the 25 ms control loop.
- Verify a newer field firmware is never downgraded by the legacy bridge.

## CTRL analogue / joystick bench

- AI0/pin 14 = physical normally-closed 5 V E-stop status only.
- AI1/pin 16 = joystick signal only.
- AGND/pin 12 = common analogue ground.
- Confirm the 249-ohm current-input shunts remain removed for voltage input use.
- Confirm E-stop is healthy high and fails unsafe on press/open/input fault.
- Confirm SGM58031 at 0x48 with no analogue fault.
- Verify calibrated joystick Left/Centre/Right gives approximately -100 / 0 /
  +100% in SRVR.
- Step joystick rapidly centre -> full travel repeatedly; reject periodic 1-2 s
  stalls or obviously stale displayed values.

## Safety/watchdog regression

- W1P independent VEL freshness watchdog remains 500 ms.
- SRVR non-zero VEL refresh remains approximately 150 ms.
- Under safe bench conditions interrupt command traffic and verify W1P stops /
  inhibits independently.
- Verify CTRL physical E-stop, W1P E-stop/internal safety, CTRL-TS link fault and
  firmware-authority mismatch all fail safe with correct source reporting.
- After every new SRVR/W1P power session, system must remain yellow
  `System | Uncalibrated` until Limit Calibration or a known Slip/re-reference is
  deliberately completed.

## Predictive limits / Leadshine / loaded-motion commissioning

Only after all display/update/safety gates above pass:

- Verify Near/Far hard limits in both directions.
- Commission predictive/dynamic soft-limit taper from low speed upward.
- Verify W1P local protection still acts if SRVR updates are interrupted.
- Confirm Leadshine communication at commissioned 115200 8N1 slave 1.
- Verify failed Modbus writes cannot trigger stale PR0 movement.
- Test Speed/Dynamic regulation unloaded/light-load first, then progressively
  increase intended slope/payload while monitoring drive/regeneration limits.

## Release acceptance archive

Archive:

- successful GitHub Actions native build logs;
- Complete Release SHA-256/checksum manifests;
- CTRL/CTRL-TS serial and SRVR logs for headless OTA;
- repeated AUX/calibration-wizard video/bench results;
- E-stop/watchdog/limit commissioning records;
- Leadshine and loaded-motion acceptance results.

## v26.10.04.06 focused bench regression

1. **Automatic firmware convergence:** leave an older compatible CTRL running, then launch the matching newer SRVR without manually rebooting CTRL/CTRL-TS. A fresh CTRL `HMI_STATUS` must be enough to schedule the update. Verify no motion enable is granted by update activity.
2. **CTRL-TS self-update handoff:** CTRL/W1P progress may remain visible on CTRL-TS. Immediately before CTRL-TS self-flash it must show `Preparing safe updater - SRVR shows self-flash progress` for about 1.8 s, then deliberately go black. During that black phase SRVR must show the increasing CTRL-TS percentage. Do not reject the release merely because the panel is black during its own safe flash.
3. **Status wording:** with limits uncalibrated, SRVR must show exactly `System | Uncalibrated`.
4. **Joystick centre readout:** complete Joystick Calibration and release the stick. Small raw/calibrated centre noise inside the configured neutral/deadband window must display as exactly `0.0%`; full travel and motion response must remain unchanged.
5. **Limit Calibration readout:** the wizard on both SRVR and CTRL-TS must show live `CURRENT POSITION` plus captured `NEAR`, `REF` and `FAR`. Each captured value must persist as the wizard advances.
6. **Virtual Limit Calibration:** with Position Source = Virtual and W1P disconnected, open Limit Calibration and use the joystick. `CURRENT POSITION` must visibly change while moving. Capture distinct Near/Far/Ref points, verify the displayed span matches the captures, and confirm no physical W1P motion command is possible.
7. **CTRL-TS geometry sync:** after calibration/settings changes, CTRL-TS must show the same Near/Far ramp boundaries as SRVR, a visible REF marker when configured, and every visible preset marker at the same normalized position. Geometry changes must appear without waiting for unrelated bulk telemetry.
8. **AUX assignment authority:** configure SRVR AUX3 = Joystick Calibration, AUX4 = Limit Calibration, AUX5 = Ref Point Slip. Reboot/reconnect CTRL and CTRL-TS. CTRL-TS must retain those live SRVR assignments and must not revert to legacy `Accel Type / Goto Ref / AUX 5` labels from persisted UIL1 layout.
9. **RS485 margin:** while normal position telemetry is changing, monitor POLL timeout/CRC/resync counters. HMG1 must be change-driven; normal live position must remain bulk-rate rather than creating continuous priority traffic.
10. Regression-check resolved behavior: confirmed AUX actions must not reboot CTRL-TS, and normal SRVR exit must return CTRL-TS immediately to the Waiting/Splash state.

- Confirm the normal green CTRL-TS status reads exactly `System | Active`, and the yellow uncalibrated status reads exactly `System | Uncalibrated`.

## v26.10.04.06 focused bench checks

- Start a newer SRVR while v26.10.04.05 CTRL/CTRL-TS are already running. Confirm firmware convergence begins without manually rebooting CTRL or CTRL-TS.
- During CTRL/W1P updates, confirm CTRL-TS shows the firmware dashboard. During CTRL-TS self-flash, confirm SRVR continues reporting the exact percentage while the panel is intentionally black.
- After any firmware dashboard returns to the normal UI, confirm within 1 second that AUX1..AUX5 names match SRVR assignments and live Speed/Position are moving.
- Confirm within 2.5 seconds that Near/Far ramp zones, Ref and preset markers match the SRVR Side View without requiring a settings change.
- Open Limit Calibration and verify the SRVR wizard matches Joystick Calibration layout: 3 step header, Side View cable graph, Near/Ref/Far boxes and live Current Position.
- Complete Near -> Far -> Ref. Confirm the wizard closes immediately on Ref and Battery Change Mode is Off in SRVR and CTRL-TS.
