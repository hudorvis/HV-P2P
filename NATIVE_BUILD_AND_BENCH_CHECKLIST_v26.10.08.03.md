# HV P2P v26.10.08.03 native build and bench checklist

## GitHub CI / source verification

- [ ] Complete source/static suite passes, including `W1P_EDGEBOX_BRAKE_DO0_1008_PASS`, `W1P_ESTOP_AI0_100803_PASS`, `LEADSHINE_COMMISSIONING_CONTRACT_PASS` and `FULL_SYSTEM_UPDATE_STATUS_1008_PASS`.
- [ ] macOS Intel / Apple Silicon and Windows backend tests pass.
- [ ] Native CTRL-TS, CTRL and W1P compilation passes.
- [ ] CTRL compilation uses the staged CTRL-TS firmware image.
- [ ] Frozen desktop smoke tests pass on all target platforms.

## EL7 RS485 commissioning

- [ ] EL7 `P05.29 = 5` (8N2), `P05.30 = 4` (38400 baud), `P05.31 = 1` (axis/slave ID 1), then restart the drive if parameters were changed.
- [ ] W1P reports the operational link at 38400/8N2/ID1 without relying on the legacy 115200/8N1 diagnostic probe.
- [ ] Confirm the drive is in the required HV P2P PR/Modbus control configuration before enabling drive writes.
- [ ] Confirm RS485 A/B and reference wiring follows the EL7/EdgeBox hardware documentation.

## Direct-brake wiring

- [ ] Brake resistance was measured with the coil unpowered/isolated; recorded value approximately 36.2 ohm.
- [ ] 24 V PSU + feeds EdgeBox pin 1 `DO_24V` and the motor-brake + lead.
- [ ] 24 V PSU 0 V feeds EdgeBox pin 3 `DO_GND`.
- [ ] Motor-brake negative/return lead connects to EdgeBox pin 5 `DO0`.
- [ ] Brake is **not** connected directly between DO0 and DO_GND.
- [ ] Leadshine physical DO4 brake wire/relay output is disconnected; DO4 remains configured logically as BRK-OFF.
- [ ] Brake branch is suitably fused and PSU/cabling are sized for measured current and voltage drop.

## Brake / E-stop bench commissioning

- [ ] With the motor safely unloaded/restrained, measure actual energized brake current; 36.2 ohm predicts roughly 0.66 A at 24 V.
- [ ] Boot/reset: DO0 remains LOW/off and brake is mechanically applied.
- [ ] Before EL7 ready/SRV-ST/BRK-OFF are verified: DO0 remains LOW/off.
- [ ] Servo Enable: EL7 logical BRK-OFF asserts, then DO0 goes HIGH/on and the brake releases.
- [ ] Normal Servo-OFF: DO0 remains on while fresh EL7 BRK-OFF is asserted, then turns off after BRK-OFF clears.
- [ ] Confirm transition-only P08.47 polling does not disturb the locked 100 ms position-feedback path.
- [ ] Verify W1P AI0 is configured for voltage input (factory 249-ohm current shunt removed, or 0-10 V hardware option).
- [ ] Wire regulated +5 V through the NC E-stop contact to AI0 pin 14; connect the 5 V 0 V return to AGND pin 12.
- [ ] With AI0 open/0 V, W1P reports `E-Stop W1P`, motion remains inhibited and DO0 cannot newly release the brake.
- [ ] With a healthy ~5 V AI0 loop, E-stop clears only after three healthy samples and still requires SRVR neutral re-arm before Servo Enable.
- [ ] Opening the AI0 loop commands immediate stop/drive-write lock/Servo-inhibit, then DO0 follows the EL7 shutdown sequence while feedback is valid; loss of brake-status authority fails DO0 LOW.
- [ ] ADC/I2C/configuration failure must report/behave as W1P E-stop active.
- [ ] Remove RS485 during a safely supported released-brake test: stale/invalid output status must fail DO0 LOW.
- [ ] Verify SRVR loss, VEL watchdog, service lock and drive alarm cannot create a new brake release.
- [ ] OTA/reboot/reset must be refused until speed is near zero, SRV-ST=0, BRK-OFF=0 and DO0=0 for two fresh samples.

## Full-system update/status check

- [ ] From a deliberately mismatched safe test set, confirm CTRL-TS shows the CTRL update row/phase/percentage while CTRL updates.
- [ ] Confirm CTRL-TS then shows the W1P update row/phase/percentage while W1P updates.
- [ ] Confirm the coordinator does not grant CTRL-TS self-update until CTRL and W1P are verified/exact.
- [ ] Confirm CTRL-TS self-update runs last and all three devices return matched after reboot.

## Locked behavior regression

- [ ] W1P normal Leadshine position feedback remains `MODBUS_POLL_MS = 100`.
- [ ] W1P independent VEL watchdog remains 500 ms.
- [ ] W1P motion profile, predictive/hard limits and velocity command path remain unchanged.
- [ ] CTRL/CTRL-TS RS485, AUX, calibration and ordinary HMI behavior remain unchanged.
- [ ] v26.10.06.11 marker-only DMP1/HMP1 smoothing remains unchanged.
- [ ] Firmware authority and automatic updating converge normally.
