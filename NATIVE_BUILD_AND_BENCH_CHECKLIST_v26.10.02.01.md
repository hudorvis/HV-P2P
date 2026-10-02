# HV P2P v26.10.02.01 Native Build and Bench Checklist

## GitHub Actions gates

- Run the complete source/protocol regression suite, including
  `test_speed_mode_contract.py` and `test_motion_innovations_contract.py`.
- CTRL-TS must compile first; embed that exact native application and SHA into
  staged CTRL before CTRL compilation.
- CTRL/W1P use the supported EdgeBox
  `PartitionScheme=app3M_fat9M_16MB` selector while sketch-local
  `partitions.csv` supplies the actual 6 MB dual-OTA slots.
- Generate the immutable SRVR firmware-authority bundle from the exact CTRL/W1P
  native applications.
- Source checkout hash must be identical before/after native firmware build.
- macOS Intel, macOS Apple Silicon and Windows x64 SRVR builds/smoke tests must
  all pass before the Complete Release is created.

## v26.10.02.01 field-feedback acceptance

- Start from a genuinely running **v26.10.01.01 CTRL + CTRL-TS**, then launch the
  GitHub-built v26.10.02.01 SRVR without installing .02/.03 first. Confirm SRVR
  detects the older CTRL, initiates the backwards-compatible update automatically,
  CTRL reboots into .04, and then its normal staged-image updater converges CTRL-TS
  to .04. No manual CTRL/CTRL-TS reboot should be required to start convergence.
- Assign an AUX tile to **Limit Calibration**. First confirmed press must open the
  wizard; subsequent confirmed presses must advance Near -> Far -> Reference -> Done
  without returning to step 1 or rebooting the display. Repeat for **Winch
  Calibration** and **Joystick Calibration**.
- Confirm **Joystick Calibration** appears in the CTRL AUX Assign drop-down.
- With the main CTRL-TS screen active, stop/close SRVR. CTRL-TS must switch to the
  original loading splash and show exactly **Waiting for SRVR**. Relaunch SRVR and
  confirm the main UI returns automatically without reboot.
- Confirm the status banner reads `E-STOP | CTRL & W1P` when both sources are
  reported, with no leading slash and no square-box glyph.
- Confirm DRIVE, SPEED, POSITION and AUX 1..AUX 5 headings contain no square-box
  replacement glyphs.
- Confirm the installed macOS SRVR app icon shows equal-size `P2P` / `SRVR` rows in
  the dark/green CTRL-TS visual style.

## CTRL / analogue-input bench

- Confirm the required factory 249-ohm 4-20 mA shunts have been removed from
  AI0/AI1 for this voltage-input commissioning.
- Joystick: +5 V -> APEM supply, 0 V -> APEM ground + EdgeBox AGND pin 12,
  proportional output -> EdgeBox **AI1 pin 16**.
- E-stop status: +5 V -> normally-closed E-stop contact -> EdgeBox **AI0 pin 14**;
  supply 0 V -> EdgeBox AGND.
- Confirm joystick voltage remains approximately full-range while connected to
  the EdgeBox, then run SRVR Left/Centre/Right calibration.
- Confirm AI0 is healthy high when the E-stop is released and goes unsafe when
  pressed/open/faulted.
- Confirm CTRL serial diagnostics show SGM58031 at 0x48 and no analogue fault.

## CTRL-TS firmware dashboard / RGB stability

1. Start a matched automatic release update with the 7-inch display visible. The
   firmware screen must be a single opaque dashboard with W1P, CTRL and CTRL-TS
   rows; an active row must show its current phase and percentage.
2. On a future update after v26.10.02.01 is already installed, confirm CTRL
   download progress appears on CTRL-TS before CTRL reboots, W1P progress is
   relayed through SRVR, and the CTRL-TS row shows local receive/write/verify.
3. During CTRL-TS local OTA, record the screen for the complete transfer. Reject
   the release if any vertical/column displacement, duplicated band, splash
   breakthrough or periodic flash remains. Source tests cannot prove RGB scanout
   stability on the physical panel.
4. Force/cancel an update only under safe bench conditions and confirm the display
   returns to its normal 16 MHz RGB clock after failure/recovery.
5. Note that the first migration *into* v26.10.02.01 cannot show the new CTRL row
   while CTRL-TS itself is still running an older UI; validate the full three-row
   experience on the following matched update or after manually commissioning this
   release.

## CTRL-TS AUX calibration wizards

- Assign an AUX card to **Limit Calibration**. Open it and complete all three
  steps. The wizard must remain visible and advance; the ESP must not reboot.
- Repeat for **Winch Calibration** and its two steps.
- Assign an AUX card to **Joystick Calibration**. Confirm Left, Centre and Right in
  sequence. A visible Joystick Calibration wizard must progress through all three
  steps and the final calibration must become active/saved.
- The assigned AUX card remains visible during the wizard. Each step uses the
  existing two-press `Confirm?`/Confirm interaction; once a step advances, the old
  `Confirmed` latch must clear immediately.
- If the display genuinely restarts, capture CTRL-TS serial output. The boot line
  `[WS-HMI] reset_reason=N` is now emitted specifically to identify the reset class.

## Joystick telemetry / calibrated readout bench

1. With CTRL and matching SRVR connected, move the joystick repeatedly through
   centre and both directions for at least 30 seconds. The SRVR Value/Percentage
   display must track continuously with no periodic 1-2 second freezes. A fast
   0 -> 100% stick step should visibly settle promptly rather than stair-step over
   roughly a second; record observed end-to-end latency on the bench.
2. Leave SRVR running long enough to cross many former two-second authority-poll
   intervals. CTRL must remain responsive; matched operation must not issue HTTP
   authority requests from the real-time loop. Confirm normal CTRL A7 telemetry is
   approximately 40 Hz (25 ms cadence) and SRVR live UI notification is 25 ms.
3. Run Left/Centre/Right joystick calibration. Immediately after the final Right
   capture, verify the Setup display reads approximately -100% at captured Left,
   0% at captured Centre and +100% at captured Right without pressing Apply.
4. Close/reopen Settings and restart SRVR; the saved calibration must remain the
   active percentage mapping, while winch *position reference* still correctly
   starts Un-Calibrated after a new session.

## Settings / Free-D auto-save

- Confirm there are no bottom Apply or Reset buttons on Settings or Free-D.
- Change representative button/combo settings and leave/re-enter the page; each
  accepted change must remain saved.
- Edit representative numeric/text fields, then press Enter or move focus away;
  the committed value must persist after SRVR restart.
- Confirm an incomplete text edit is not written character-by-character.
- Change Free-D output IP/port/rate and geometry/weight values and verify output
  and diagrams use the committed values immediately.
- Exercise W1P IP change only under safe commissioning conditions and verify the
  existing transactional readdress succeeds or the edit is rejected without
  orphaning W1P.

## Joystick centre-drift commissioning

1. Complete normal joystick calibration and verify Percentage reaches expected
   negative/zero/positive values.
2. Leave the system stationary with the joystick released for at least 5 s.
3. Warm the enclosure/controls through a realistic operating period and verify a
   small centre-voltage drift does not produce a non-zero motion request.
4. Verify the automatic correction remains slow and small; it must not change the
   saved Left/Centre/Right calibration values after restart.
5. Deliberately create/measure a centre error larger than the bounded trim only
   during a safe non-motion test and verify SRVR recommends recalibration instead
   of silently learning a large offset.

## Predictive stopping / dynamic soft limits

Commission this from low speed upward with an unloaded/light-load system first.
For both Near and Far directions:

1. Verify the existing absolute limit still blocks outward movement at the limit.
2. Approach from well inside the span with a steady joystick command and verify
   commanded speed begins tapering before the endpoint.
3. Repeat at increasing speed and confirm the taper starts farther from the limit
   as stopping distance increases.
4. Confirm motion remains smooth through the existing user ramp zone and the
   predictive envelope; the more restrictive limit should win.
5. Simulate/deliberately interrupt SRVR updates only under safe bench conditions
   and verify W1P's local limit cap plus the 500 ms VEL watchdog remain effective.
6. Do not approve full-speed operation until measured stopping distance remains
   comfortably inside the calibrated limits in both directions and under the
   worst intended load/slope.

## Speed mode / incline-load commissioning

Use **Speed** acceleration mode and start with conservative speed/accel values.
The goal is constant cable speed, not constant motor power.

1. On level/light load, compare W1P `REQ_VEL_MPS`, `PROFILE_VEL_MPS`,
   `CMD_VEL_MPS` and measured `VEL_MPS` at several steady joystick positions.
2. Uphill: verify actual velocity remains close to target while the servo supplies
   the additional torque/current required by gravity/load. W1P correction may
   increase the velocity command slightly but must remain bounded.
3. Downhill: verify the servo holds the same commanded direction/speed and does
   not free-run/overspeed. Braking should be produced as negative/regenerative
   torque inside the Leadshine velocity loop; W1P must not flip command sign just
   to brake.
4. Watch Leadshine DC-bus/regeneration/over-voltage alarms and resistor heating.
   A long or heavy downhill run may exceed the internal regenerative resistor's
   energy capacity and require the drive manufacturer's external regenerative
   resistor arrangement.
5. Repeat in both cable directions and at the maximum intended payload only after
   the low-energy tests are stable.

## CTRL <-> CTRL-TS preset-name check

- Set Preset Names = **Short Names** and confirm SRVR Top View, Side View and
  CTRL-TS all show `P1`...`P10` consistently.
- Set Preset Names = **Long Names**, edit several preset names in SRVR, and
  confirm the same long labels appear on both SRVR diagrams and CTRL-TS.
- Confirm changing name display mode does not change preset positions or motion.

## CTRL <-> CTRL-TS RS485 / OTA

- Continuity: EdgeBox pin 7 -> Waveshare A; pin 8 -> Waveshare B; no A/B short.
- About 60 ohms across A/B when both 120-ohm endpoint terminations are active.
- Verify bootstrap/SHA mismatch performs stable FW_BEGIN/FW_BLOCK/FW_END transfer,
  exact SHA verification, reboot and a fresh HELLO/COMPATIBLE session.
- Verify stale detected TS identity clears after link timeout.

## W1P <-> Leadshine

- Use the custom RS485 mapping, not a straight-through RJ45 cable.
- EdgeBox pin 7 -> Leadshine 485+; EdgeBox pin 8 -> Leadshine 485-; intended
  far-end termination present.
- Confirm P05.29=4, P05.30=6, P05.31=1 and restart the drive after changes.
- Operational link must become Connected at 115200 8N1 slave 1.
- Verify Modbus exceptions are reported as exceptions, a failed velocity write
  cannot trigger stale PR0, and the independent 500 ms VEL watchdog stops/inhibits
  the drive.

## Release acceptance

Do not treat the source ZIP alone as a proven machine release. Preserve the
GitHub Complete Release ZIP/checksums and the successful bench logs for
CTRL/CTRL-TS, W1P/EL7, predictive limits and incline Speed-mode testing.
