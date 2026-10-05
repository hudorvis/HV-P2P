# HV P2P v26.10.06.02 native-build and bench checklist

## 1. GitHub gates

1. Replace the repository with this complete source tree.
2. Run the normal GitHub Actions workflow.
3. Require the complete source/protocol suite, native firmware build/staging, firmware-authority bundle, macOS Intel, macOS Apple Silicon and Windows jobs to pass.
4. Do not substitute locally fabricated firmware binaries.

## 2. Locked-scope verification

Confirm the release diff contains no unrelated production changes. Functional production changes should be confined to:

- SRVR `backend.py` — CTRL-coherent background VEL lease renewal;
- Run `Main.qml` — System captions/grid;
- Settings `SetupPage.qml` — AUX `None` ordering;
- CTRL-TS firmware — display-only progress-marker interpolation.

CTRL and W1P firmware behavior must remain unchanged apart from release identity.

## 3. Limit Calibration long-travel test

1. Start with a valid existing calibration and open Limit Calibration.
2. Capture Near and confirm Current Winch Position re-zeros to 0.00 m.
3. Hold a steady joystick command and travel continuously beyond the previously observed ~15 m and ~17 m points toward Far.
4. Expected: no unexplained W1P VEL-watchdog stop and no forced neutral cycle during healthy steady motion.
5. Change the physical joystick materially while moving. Expected: the background bridge stops renewing the old command; the normal motion loop follows the new joystick value.
6. Test a genuine E-stop/CTRL fault or loss of CTRL packets. Expected: stale VEL renewal does not continue; motion stops and the existing joystick-neutral re-arm remains required.
7. Confirm W1P `W1P_VEL_COMMAND_TIMEOUT_MS` is still 500 ms and normal SRVR refresh remains ~150 ms.

If motion still stops unexpectedly, capture SRVR logs plus W1P serial output covering at least 20 seconds before/after the event, especially `SAFETY_SRC`, `VEL_WD`, `SERVICE_LOCK`, RS485/drive state and CTRL flags.

## 4. Run > Shortcuts UI

System tab:

- row height visually matches Preset 1-5 / Preset 6-10 / Limits;
- row spacing and value/button heights are consistent;
- Power/Speed, Off/On, Drive Mode and Preset Names stay fully inside the panel;
- calibration captions are exactly `Joystick`, `Limit`, `Winch`.

No other Run-page layout should change.

## 5. Settings AUX ordering

Open each CTRL AUX Assign drop-down and confirm `None` is the first option. Existing assignments/actions must remain available and saved values must still resolve correctly.

## 6. CTRL-TS progress marker

1. Move at low speed and confirm the skate marker tracks the verified position normally.
2. Increase speed and observe the progress marker across a long travel.
3. Expected: marker movement is visibly fluid rather than moving in ~10 Hz steps.
4. Compare the numeric Current Position to SRVR/W1P telemetry; it must remain verified telemetry, not a predicted number.
5. Stop abruptly and confirm the marker converges/holds with the next verified sample and does not run away; local prediction is capped at 180 ms.
6. Confirm RS485 motion transport remains the established HMM1 cadence/budget.

## 7. Preserved regression checks

- automatic firmware order/reboot convergence from `.06.01`;
- transactional Limit Calibration Cancel/rollback;
- CTRL-TS AUX EVENT ACK/retry serialization;
- AI0 E-stop / AI1 joystick mapping;
- W1P 500 ms VEL watchdog;
- hard limits and predictive/dynamic soft limits;
- Leadshine velocity architecture;
- Current Speed positive to operator while signed transport/control is retained.
