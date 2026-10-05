# HV P2P v26.10.05.07 native-build and bench checklist

## Release gate

1. Require `ALL_SOURCE_CHECKS_PASS` from the final `.05.07` source tree.
2. Run GitHub Actions and require the PySide backend runtime regression to pass with dependencies installed.
3. Require native CTRL, W1P and CTRL-TS compilation from the repository workflow. GitHub Actions/native compilation remains authoritative; do not substitute locally fabricated binaries.
4. Confirm the staged CTRL carrier contains the natively built matching `.05.07` CTRL-TS image before CTRL is compiled.

## Firmware update / final reboot

- Start `.05.07` SRVR with the previous working CTRL/W1P/CTRL-TS release already running; do not manually reboot ESP32 nodes to begin convergence.
- Confirm update ordering remains CTRL -> W1P -> CTRL-TS.
- During CTRL-TS self-flash, confirm the physical screen remains intentionally headless/black while SRVR shows progress.
- At 100%/verified image, confirm CTRL logs `reboot command acknowledged; awaiting new boot identity` rather than declaring success on ACK alone.
- Confirm CTRL-TS restarts automatically and CTRL then logs a different old/new `boot_id` plus exact-image confirmation.
- Repeat from the oldest `safe_ota=2` touchscreen firmware you still support in the field. No manual touchscreen reset should be required after the verified image is selected.

## CTRL-TS layout

- On the normal Run display, inspect endpoints and several preset configurations including presets close to Near and Far.
- Confirm NEAR/FAR numeric distances, REF label/marker, current skate marker, ramp wedges and all visible preset names remain readable with no vertical overlap.
- Confirm the AUX tiles remain visually consistent with the approved design and touch targets remain reliable.
- Confirm no operator font is smaller than the existing Montserrat 10 small Drive/Acceleration text.

## Calibration Cancel / transaction

### Joystick Calibration

- Open from SRVR and from a CTRL-TS AUX assignment.
- Before capture, LEFT/CENTRE/RIGHT must show `-` on CTRL-TS.
- Capture Left only, press Cancel, and verify the previously saved Left/Centre/Right values remain unchanged.
- Repeat after Left+Centre.
- Confirm Cancel exits the overlay, commands zero motion and requires joystick neutral before normal motion can resume.

### Limit Calibration

- Begin with a known valid Near/Far/Ref and Winch Invert state.
- Before capture, Near/Ref/Far must show `-` on CTRL-TS.
- Capture Near, then Cancel. Verify the previous Near/Far/Ref, span and Winch Invert are unchanged.
- Capture Near+Far, including a run where Far travel implies automatic Winch Invert correction, then Cancel. Verify no partial new limit or invert value was saved/applied.
- Complete Near -> Far -> Ref and verify all staged values commit together only on Ref.
- Verify cancellation from an initially uncalibrated system returns to `System | Uncalibrated`; cancellation from an already calibrated system returns to its previous safe state.

## Limit Calibration continuous travel

- While travelling Near -> Far at the reduced service speed, hold a steady non-zero joystick command for an extended run.
- Confirm the skate does not stop at arbitrary points and does not require repeated neutral toggles.
- Put SRVR behind another macOS application during the run and repeat.
- Confirm W1P `VEL_WD` remains clear during healthy operation and the normal non-zero VEL cadence is approximately 150 ms.
- Deliberately terminate/freeze SRVR control traffic and confirm W1P still trips its unchanged 500 ms VEL watchdog, stops, inhibits Servo Enable and requires neutral re-arm after recovery.

## Background-link reliability / false red state

- Leave SRVR running while repeatedly foregrounding other macOS applications for several minutes.
- Confirm CTRL-TS does not flash red merely because SRVR is backgrounded.
- Confirm closing SRVR still takes CTRL-TS promptly to Waiting/Splash via explicit `SRVR_OFFLINE`.
- During Limit Calibration, watch SRVR logs for `[W1P STATUS] rejected frame ...`. One rejected frame—including a corrupt safety token or non-finite numeric value—must not immediately change the authoritative banner to red while the previous valid status is still fresh.
- Disconnect W1P/Leadshine or trigger a genuine E-stop and verify red still takes priority immediately/after the existing freshness rules as appropriate.

## Current Speed regression

- Command motion in both directions.
- SRVR and CTRL-TS Current Speed must display a positive magnitude.
- DSP1/HMM1/internal velocity must retain signed direction.
- Predictive stopping and physical motion direction must remain unchanged.

## Existing safety/communications acceptance

Re-run the existing `.05.06`/`.05.04` commissioning checks for AI0 E-stop, AI1 joystick, hard limits, ramp/predictive stopping, CTRL<->CTRL-TS EVENT ACK/retry, Battery Change Mode, Virtual Position Source, Leadshine feedback/Servo Enable/brake handling and firmware authority. This revision does not intentionally weaken those paths.
