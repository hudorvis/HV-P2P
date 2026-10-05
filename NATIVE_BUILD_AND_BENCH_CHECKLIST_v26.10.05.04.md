# HV P2P v26.10.05.04 Native Build and Bench Checklist

## Release gate

1. Require `ALL_SOURCE_CHECKS_PASS` from the final `.05.04` source layout.
2. Run GitHub Actions native firmware and desktop jobs; native compilation remains authoritative.
3. Use only matching `.05.04` staged firmware/desktop artifacts.
4. Bench-test with the winch unable to move before unloaded/loaded commissioning.

## 1. Automatic firmware update and post-update return

- Start older compatible CTRL/W1P/CTRL-TS, then launch `.05.04` SRVR without manually rebooting nodes.
- Verify existing `.05.03` firmware-coordinator behavior still converges in CTRL -> W1P -> CTRL-TS order.
- CTRL-TS may be black during its own actual flash; SRVR must continue showing its progress.
- After CTRL-TS reports a verified/finalized image, do not manually reboot it. It must return to the new application automatically even if CTRL's final `REBOOT` packet is deliberately lost. Expected autonomous fallback is about 2.5 s after verification; a received explicit reboot command may return sooner.
- Reject if a successfully finalized touchscreen remains black indefinitely.

## 2. Limit Calibration motion override

With old Near/Far limits already configured:

- Open Limit Calibration.
- Hold the joystick continuously toward and through an old end limit.
- The operator must not need to release/toggle/reapply the joystick merely to cross the old software calibration boundary.
- Confirm W1P receives `SERVICE_MODE 1` promptly and STATUS subsequently confirms service mode.
- Close/complete calibration and confirm normal service-mode synchronization restores the intended protected operating state.
- Physical E-stop, link safety and independent watchdog behavior must remain active throughout.

## 3. Calibration wizard presentation

### SRVR Limit Calibration

- Three-step flow remains Near -> Far -> Ref & Done.
- Show Near / Ref / Far captured values and `Current Winch Position`.

### CTRL-TS Limit Calibration

- Show three clearly separated Near / Ref / Far value boxes.
- Show `Current Winch Position` on the row beneath.
- Values must update during capture and match SRVR.

### CTRL-TS Joystick Calibration

- Show three Left / Centre / Right value boxes.
- Show `Current Joystick Position` on the row beneath.
- Prompts remain the approved Left / Centre / Right instructions.

## 4. Current Speed presentation

Test motion in both directions in Virtual mode and, later, safe unloaded hardware mode.

- Directional control/motion must remain correct.
- All operator-facing Current Speed readouts on SRVR and CTRL-TS must show positive magnitude only (for example `5.0 km/h`, never `-5.0 km/h`).
- Do not reject signed internal velocity in logs/control variables where direction is required.

## 5. CTRL-TS Near/Far graph width and alignment

- The primary travel line should extend nearly the full display/content width rather than starting after the NEAR label and ending before FAR.
- Near/Far, ramp zones, skate marker, REF and presets must still use the same normalized coordinates and remain within visible bounds.
- Verify end markers reach the intended Near/Far endpoints without clipping.

## 6. SRVR Run > Shortcuts

Verify:

- Acceleration Mode Power / Speed forms one full-width two-button row.
- Battery Change Mode On / Off forms one full-width two-button row.
- Calibration Mode has three equal actions: Joystick Calibration / Limit Calibration / Winch Calibration.
- Preset Names Short Names / Long Names layout remains aligned below.

## 7. SRVR Settings > Calibration

Top-to-bottom order must be:

1. Joystick Calibration
2. Limit Calibration
3. Winch Calibration

Each button must open the correct wizard.

## 8. SRVR Settings > AUX Assign ordering

- Non-preset options must be alphabetically ordered by displayed action name.
- Preset Save / Recall / Slip option groups remain grouped at the bottom.
- Assign several actions, verify the saved assignment and confirm CTRL-TS labels/actions match SRVR after reconnect/update.

## 9. Safety invariants

Confirm no regression to:

- W1P independent VEL freshness watchdog = 500 ms;
- SRVR non-zero VEL refresh approximately 150 ms;
- CTRL AI0 physical E-stop / AI1 joystick mapping;
- W1P DI0 E-stop;
- hard limits and predictive/dynamic soft limits outside explicit service override;
- Leadshine closed-loop velocity architecture;
- software Servo Enable remains inhibited until SRVR's explicit neutral-verified re-arm.

## 10. Acceptance archive

Archive successful GitHub native build logs plus bench evidence for continuous crossing of an old limit in Limit Calibration, CTRL-TS autonomous post-OTA reboot, matching calibration readouts, positive speed presentation, full-width CTRL-TS position graph, and requested SRVR shortcut/settings layouts.
