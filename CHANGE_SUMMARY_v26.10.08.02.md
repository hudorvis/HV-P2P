# HV P2P v26.10.08.02 change summary

Date: 2026-10-08

Source baseline: `v26.10.06.11` (the locked `v26.10.06.10` system plus the approved CTRL-TS marker-smoothness path).

This revision changes only the **W1P ↔ Leadshine RS485 commissioning format**, the **W1P physical motor-brake output path**, the matching SRVR physical-brake status field, and release/test documentation. CTRL motion/control, CTRL-TS UI/RS485 behavior, W1P motion profiles/limits, calibration, AUX behavior, updater/firmware authority, watchdogs and all unrelated approved behavior remain locked.

## W1P ↔ EL7 RS485

The operational W1P Leadshine link now matches the EL7-RS factory communication defaults:

- 38400 baud
- 8 data bits, no parity, 2 stop bits (`8N2`)
- Modbus slave/axis address 1
- expected EL7 parameters: `P05.29=5`, `P05.30=4`, `P05.31=1`

The former HV setting, 115200/8N1, is retained only as a **read-only diagnostic probe** while W1P is stopped, write-locked and Servo Enable inhibited. A diagnostic response never promotes link health; W1P always restores 38400/8N2 for normal operation.

## EdgeBox DO0 motor-brake output

The `ELM2M-2000LB130E-H` 24 V spring-applied brake is now switched by **W1P EdgeBox DO0 / GPIO40** instead of the Leadshine physical DO4 plus an external brake relay.

EdgeBox multi-function connector wiring is pin 1 `DO_24V`, pin 3 `DO_GND`, and pin 5 `DO0`. The brake positive lead goes to the +24 V rail feeding pin 1; the brake negative/return lead goes to pin 5. Pin 3 goes to the 24 V supply 0 V. The coil is **not** wired between DO0 and DO_GND.

With the measured 36.2 ohm brake resistance, the nominal estimate is approximately **0.663 A at 24 V / 15.9 W**. Hardware commissioning must still verify real current and thermal behavior.

## Brake timing and fail-safe behavior

The EL7 remains the **logical brake timing authority**. DO4 stays configured internally as `BRK-OFF`, but its physical output terminal is unused. W1P reads the logical `BRK-OFF` state over Modbus and uses that verified state to control EdgeBox DO0.

DO0 polarity is deliberately fail-applied: **DO0 HIGH/on energises the coil and releases the brake; DO0 LOW/off removes brake power and applies the spring brake.** DO0 is latched LOW before network, Modbus, updater or motion startup. A new brake release requires the existing healthy/ready gates plus fresh EL7 feedback, verified DO4 assignment, SRDY, SRV-ST and asserted logical BRK-OFF.

During an orderly stop/E-stop W1P does not use the holding brake as a dynamic brake. It commands the normal stop/Servo-inhibit path and, while fresh EL7 feedback remains available, follows the EL7 BRK-OFF shutdown timing. During that transition only `P08.47` is refreshed at a 25 ms minimum interval; the locked 100 ms normal position-feedback cadence is unchanged. Loss or staleness of brake-status/RS485 authority fails DO0 LOW.

The **local W1P DI0 E-stop remains active** in this release; there is no E-stop bypass in v26.10.08.02.

## Firmware updating / CTRL-TS status

The existing firmware-authority architecture is retained. CTRL and W1P both publish authority-update progress to SRVR. SRVR carries both CTRL and W1P phase/percentage fields in DSP1, CTRL forwards them to CTRL-TS in priority HMS1 state traffic, and CTRL-TS renders separate CTRL and W1P update rows.

The coordinator remains ordered **CTRL → W1P → CTRL-TS**, so CTRL-TS stays operational to display CTRL and W1P progress before its own final-stage self-update. The new brake output is included in W1P safe-service entry: OTA/reboot/reset requires fresh proof of near-zero speed, SRV-ST off, logical BRK-OFF off and physical EdgeBox DO0 off for two consecutive samples.

## SRVR status

W1P reports both `BRAKE_OUT` (EL7 logical BRK-OFF state) and `BRAKE_DO0` (physical EdgeBox brake-release command). SRVR requires both fields and uses `BRAKE_DO0` for the operator-facing brake state.

## Locked areas

CTRL and CTRL-TS production behavior is unchanged apart from release identity. The `.06.11` DMP1/HMP1 marker path and all approved `.06.10` motion, safety, calibration, AUX and updater behavior are retained.
