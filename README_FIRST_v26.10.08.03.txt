HV P2P v26.10.08.03 - GitHub Ready Source
================================================
Source baseline: v26.10.08.02.

THIS REVISION
-------------
The only functional production change is the W1P local E-stop input:

  OLD: EdgeBox DI0, 24 V NC loop
  NEW: EdgeBox AI0, 5 V NC status loop

W1P AI0 wiring on the commissioned connector:
  pin 14 AI0 = +5 V through the normally-closed E-stop contact
  pin 12 AGND = 5 V supply 0 V

Firmware behaviour:
  3.5..6.0 V = healthy sample
  open / low / mid-band / over-range / ADC fault = E-stop active
  assertion = immediate at the next 10 ms sample
  clearing = 3 consecutive healthy samples
  startup = fail-closed until AI0 is proven healthy

IMPORTANT HARDWARE REQUIREMENT
------------------------------
This 5 V voltage-input firmware assumes W1P AI0 is configured like the commissioned
CTRL EdgeBox: the factory 249-ohm 4-20 mA shunt on AI0 has been removed, or the unit
is the 0-10 V analogue-input hardware option. Do not use PGND/GND/DO_GND as the
analogue return; use AGND.

PRESERVED FROM v26.10.08.02
---------------------------
- EL7 Modbus: 38400 baud / 8N2 / slave ID 1.
- EdgeBox DO0 directly switches the 24 V spring-applied motor brake; LOW/off applies
  the brake and HIGH/on releases it under verified EL7 BRK-OFF sequencing.
- CTRL -> W1P -> CTRL-TS automatic update order and update progress screen.
- Motion, limits, calibration, AUX, watchdog, firmware-authority and UI behaviour.

See W1P_ESTOP_WIRING_v26.10.08.03.md,
W1P_BRAKE_WIRING_v26.10.08.03.md and
NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.10.08.03.md before powered commissioning.

No firmware binaries are included in this source package. Native Arduino compilation
and physical hardware commissioning remain the GitHub Actions / bench gates.
