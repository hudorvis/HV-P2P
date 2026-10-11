HV P2P v26.10.08.04 - GitHub Ready Source
================================================
Source baseline: v26.10.08.03.

THIS REVISION
-------------
1) Restores the established W1P <-> Leadshine EL7 Modbus settings:
     115200 baud / 8N1 / slave ID 1
     P05.29 = 4
     P05.30 = 6
     P05.31 = 1

   The EL7 factory 38400/8N2 format is retained only as a stopped, read-only
   diagnostic probe. Restart the EL7 after changing P05 communication settings.

2) Adds useful Leadshine/RS485 fault reporting to the SRVR Log page and saved log.
   SRVR now reports no-response, factory-format detection, parameter mismatch,
   configuration-read fault, feedback/SRDY fault and verified recovery instead of
   only showing a generic RS485 Disconnected state.

PRESERVED FROM v26.10.08.03
---------------------------
- W1P local E-stop: AI0 / 5 V fail-closed status loop.
- EdgeBox DO0 directly switches the 24 V spring-applied motor brake; LOW/off applies
  the brake and HIGH/on releases it under verified EL7 BRK-OFF sequencing.
- CTRL -> W1P -> CTRL-TS automatic update order and update progress screen.
- Motion, limits, calibration, AUX, watchdog, firmware-authority and UI behavior.

W1P AI0 wiring on the commissioned connector:
  pin 14 AI0 = +5 V through the normally-closed E-stop contact
  pin 12 AGND = 5 V supply 0 V

IMPORTANT AI0 HARDWARE REQUIREMENT
----------------------------------
The W1P 5 V E-stop input assumes AI0 is configured for voltage input like the
commissioned CTRL EdgeBox (factory 249-ohm current shunt removed, or 0-10 V input
hardware option). Use AGND for the analogue return.

See W1P_ESTOP_WIRING_v26.10.08.04.md,
W1P_BRAKE_WIRING_v26.10.08.04.md and
NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.10.08.04.md before powered commissioning.

No firmware binaries are included in this source package. Native Arduino compilation
and physical hardware commissioning remain the GitHub Actions / bench gates.
