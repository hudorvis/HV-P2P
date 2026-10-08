# HV P2P v26.10.08.03 deep code audit

Date: 2026-10-08
Baseline: `v26.10.08.02`

## Scope lock

The requested change is isolated to the **W1P local E-stop acquisition path** plus release identity/tests/documentation. CTRL, CTRL-TS and SRVR production logic is unchanged apart from release identity. W1P Leadshine Modbus, motion profile, limits, watchdogs, firmware authority, DO0 brake sequencing and updater/service gates remain the reviewed `.08.02` implementations.

## W1P AI0 acquisition

- `Wire` uses the EdgeBox fixed I2C pins SDA GPIO20 / SCL GPIO19.
- W1P uses onboard `SGM58031` address `0x48`.
- AI0 is configured continuous at 800 SPS, ±6.144 V ADC range (`0x40E3`), matching the project's CTRL driver.
- The commissioned voltage-input front end is treated as approximately 2:1, so field voltage is reconstructed as ADC voltage ×2.
- Sampling is bounded to 10 ms minimum interval; no busy-loop polling is introduced.
- The AI0 config register is verified before every accepted sample. Read/config failure is unsafe.
- A lost ADC is retried at 1 s intervals, but local E-stop remains active until three fresh healthy samples have been proven after recovery.

## E-stop semantics

- `WinchState.local_estop` initializes `true`.
- 3.5–6.0 V is the only healthy voltage window.
- Assertion is immediate for low/open/mid-band/over-range or ADC/config failure.
- Clearing requires 3 consecutive healthy samples.
- On transition active, the established path remains `driveStopNow()`, `g.drive_writes_enabled = false`, `requestSoftwareSrvonInhibit(true, "W1P_ESTOP")`.
- Clearing never directly restores Servo Enable; SRVR neutral-return re-arm remains required.
- `edgeboxBrakeReleaseStartAllowed()` still rejects `g.local_estop`, and brake shutdown sequencing still treats it as a stop source.

## Hardware assumption

The firmware conversion deliberately matches the commissioned CTRL voltage-input hardware. W1P AI0 therefore requires the factory 249-ohm current shunt removed, or an EdgeBox 0–10 V analogue-input option. Connector labels on the commissioned project unit are AI0 pin 14 and AGND pin 12.

## Preserved Leadshine / brake contract

Normal EL7 communication remains 38400/8N2/ID1 with expected `P05.29=5`, `P05.30=4`, `P05.31=1`. The prior 115200/8N1 path remains a stopped/read-only diagnostic probe only. EdgeBox DO0 remains the physical low-side brake switch; brake release continues to require fresh verified EL7 SRV-ST/BRK-OFF authority, and lost/stale authority fails DO0 LOW.

## Update/status contract

The existing updater remains ordered CTRL → W1P → CTRL-TS. CTRL and W1P authority-update phase/percentage remain forwarded through SRVR/CTRL to the CTRL-TS update screen. Safe W1P service entry still requires stopped motion, Servo Enable off, logical BRK-OFF off and physical DO0 off before OTA/reboot/reset.

## Regression locks

- `test_w1p_estop_ai0_100803.py` proves AI0 acquisition, fail-closed startup, healthy window, 3-sample clear, established stop/Servo-inhibit action and brake gating.
- `validate_edgebox_integration.py` hash-locks `initW1pEstopAI0`, the three SGM58031 helper functions and `updateLocalInputs`.
- Existing `.08.02` direct-brake, EL7 commissioning and full-system updater tests remain enabled.
- Historical CTRL/CTRL-TS/SRVR/motion/calibration/AUX/updater regressions remain in `run_all_source_checks.py`.
