# HV P2P v26.10.06.02 change summary

Date: 2026-10-06

Locked baseline: `v26.10.06.01`. This revision intentionally changes only the five operator/bench items requested after `.06.01`. No unrelated production refactor or UI redesign is included.

## 1. Limit Calibration intermittent stops

Observed symptom: during a long Limit Calibration move, motion could stop at an arbitrary cable position and would not resume until the joystick returned through neutral.

The neutral-return requirement is the existing safety interlock and remains unchanged. The source audit confirmed normal Near/Far software-limit enforcement is bypassed while Limit Calibration service mode is active, so fixed stops around 15 m or 17 m are not programmed calibration distance limits.

The remaining scheduling vulnerability was the short non-zero VEL refresh bridge. The normal SRVR control loop refreshes non-zero VEL at approximately 150 ms and W1P independently stops if no fresh VEL arrives for 500 ms. The bridge lease was renewed only by the Qt motion loop for 220 ms. A sufficiently long Qt/UI scheduling pause could therefore allow the bridge to expire and W1P to correctly trip its independent watchdog, after which SRVR correctly requires joystick neutral.

`.06.02` keeps every timing/safety limit unchanged and instead lets fresh CTRL UDP packets renew the existing short bridge lease only while:

- the physical joystick sample remains within 0.035 of the sample that produced the active VEL command; and
- CTRL reports no E-stop, analogue/ADC, HMI-link or firmware fault flag.

If the joystick changes, returns toward zero, CTRL reports a relevant fault, CTRL packets stop, or SRVR explicitly sends zero/STOP, renewal stops immediately. The actual velocity command is still produced only by the normal motion loop. W1P's independent 500 ms watchdog remains unchanged and authoritative.

Without a serial/network trace captured at the exact previous stop, the historical 15 m / 17 m events cannot be proven retrospectively to be the watchdog. This revision closes the concrete scheduling hole that produces the exact stop-plus-neutral-rearm symptom while preserving the independent safety layers.

## 2. Run > Shortcuts > System calibration captions

The three System-tab calibration buttons now read:

- `Joystick`
- `Limit`
- `Winch`

Only the Run/Shortcuts captions changed. The backend calibration actions and Settings AUX assignment names remain `Joystick Calibration`, `Limit Calibration` and `Winch Calibration`.

## 3. Settings AUX Assign ordering

`None` is now the first entry in the shared CTRL AUX assignment drop-down. All other assignments are retained.

## 4. CTRL-TS progress marker smoothing

The position source remains the verified W1P/Leadshine position carried through SRVR as `pos_frac`. The existing HMM1 motion packet remains approximately 10 Hz; no control or safety protocol rate was increased.

The visible skate marker now runs from the CTRL-TS local UI loop at approximately 50 Hz. Between verified HMM1 samples it uses signed measured speed to interpolate the marker, with prediction bounded to 180 ms. Each new verified position sample continuously corrects the display. The numeric Current Position remains the verified telemetry value and is not predicted.

This is presentation-only smoothing and cannot command or alter winch movement.

## 5. Run > Shortcuts > System geometry consistency

The System tab now uses the same locked control grid as the other Shortcut tabs:

- 31 px row height;
- 3 px row spacing;
- 5 px control gaps;
- standard `HVButton` / `HVField` fonts rather than smaller per-control overrides;
- existing 150 px label/action-column alignment retained.

This preserves the approved layout allocation while making the System rows visually consistent with Preset 1-5, Preset 6-10 and Limits.

## Locked production scope

After normalising the version string, only four production files differ from `v26.10.06.01`:

1. `SRVR_GitHub_v26.10.06.02/backend.py`
2. `SRVR_GitHub_v26.10.06.02/qml/Main.qml`
3. `SRVR_GitHub_v26.10.06.02/qml/pages/SetupPage.qml`
4. `HV_P2P_CTRL_TS_v26.10.06.02/HV_P2P_CTRL_TS_v26.10.06.02.ino`

CTRL and W1P firmware logic are unchanged apart from release identity.

## Preserved safety/control contracts

- W1P independent VEL freshness watchdog: **500 ms unchanged**.
- Normal SRVR non-zero VEL refresh: approximately **150 ms unchanged**.
- AI0 E-stop / AI1 joystick mapping unchanged.
- Joystick-neutral safety re-arm unchanged.
- Hard limits, predictive stopping/dynamic soft limits and Leadshine velocity architecture unchanged.
- CTRL <-> CTRL-TS isolated half-duplex RS485 single-flight EVENT ACK/retry behavior unchanged.
- Automatic firmware ordering/reboot convergence from `.06.01` unchanged.

## Verification

`python3 tools/run_all_source_checks.py` passes in full:

- 370 EdgeBox integration checks;
- all historical bench/update/RS485/calibration regressions;
- new `test_bench_regression_0602.py` coverage for all five requested changes;
- 53 build-pipeline checks;
- Modbus, SRVR wire, speed and motion contracts;
- release consistency and source hygiene;
- Python syntax across 56 files; and
- SRVR project preflight.

PySide6 is not installed in this source-audit environment, so the PySide runtime test remains a GitHub desktop-build gate. Native ESP32 compilation also remains GitHub Actions authoritative. No local firmware binaries are fabricated.
