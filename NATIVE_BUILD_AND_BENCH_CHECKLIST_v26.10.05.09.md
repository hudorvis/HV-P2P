# HV P2P v26.10.05.09 native-build and bench checklist

## 1. GitHub native build gate

1. Upload this complete source tree to the GitHub Actions repository.
2. Require the native firmware job to compile in order: CTRL-TS -> staged CTRL -> W1P.
3. Confirm CTRL compilation passes the previous `newBootId was not declared in this
   scope` point in `handleHmiFrame()`.
4. Require the generated matched firmware authority bundle and desktop jobs to pass.
5. Do not substitute locally fabricated firmware binaries for GitHub artifacts.

## 2. Firmware update final reboot

- Start from an older supported `safe_ota=2` CTRL-TS firmware.
- Perform normal update order CTRL -> W1P -> CTRL-TS.
- During CTRL-TS self-write, black/headless display is expected.
- After verified FW_RESULT, confirm CTRL does not mark update complete merely on
  REBOOT ACK.
- Confirm CTRL-TS restarts autonomously and returns with the new application,
  without manual power/reset.
- Confirm SRVR reports the exact new CTRL-TS version and update completion.

## 3. CTRL-TS layout

- Check Near and Far names/values, REF, skate marker, ramp wedges and all visible
  Preset Position names across near/middle/far positions.
- No vertical/horizontal text overlap is acceptable.
- Verify smallest relevant text remains at least the current Montserrat 10 size.

## 4. Calibration Cancel/transaction

Joystick Calibration:
- Before capture, Left/Centre/Right show `-`.
- Cancel at each step; previous saved calibration must remain unchanged.
- Confirm motion remains stopped and neutral is required before normal re-arm.

Limit Calibration:
- Before capture, Near/Far/Ref show `-`.
- Cancel after Near, after Far, and before final Ref.
- Existing saved Near/Far/Ref, span and Winch Invert must remain unchanged.
- Complete Near -> Far -> Ref and confirm all values commit together only at Ref.

## 5. Limit Calibration motion reliability / red-state regression

- Travel repeatedly from Near toward a new Far at calibration service speed.
- Confirm no random stop/red flash occurs from a malformed/incomplete single W1P
  STATUS or PONG.
- If a real E-stop, W1P loss, RS485/Leadshine fault, firmware mismatch or 500 ms VEL
  watchdog occurs, red must still take priority and joystick neutral must still be
  required before re-arm.
- Review logs for `[W1P STATUS] rejected frame` if any malformed telemetry occurs.

## 6. macOS background operation

- Run SRVR on macOS, make another application foreground for several minutes.
- Confirm CTRL and CTRL-TS remain connected and do not flash red merely because
  SRVR is behind another window.
- While safe/unloaded, hold a steady calibration/manual command and confirm normal
  ~150 ms VEL traffic remains healthy through brief GUI scheduling delays.
- Quit SRVR normally and confirm CTRL-TS returns promptly to Waiting/Splash.

## 7. Preserved safety checks

- W1P independent VEL freshness watchdog is still exactly 500 ms.
- AI0 E-stop and AI1 joystick mapping unchanged.
- Hard limits/predictive stopping remain active in normal mode.
- Battery Change and calibration service travel retain reduced-speed limit bypass
  semantics only while their service mode is active.
- Virtual Position Source never emits physical non-zero W1P velocity.
- Current Speed is positive magnitude on SRVR/CTRL-TS while reverse wire velocity
  remains negative.
