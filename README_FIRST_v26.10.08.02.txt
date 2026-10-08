HV P2P v26.10.08.02 - GitHub Ready Source
================================================
Source baseline: v26.10.06.11, preserving the locked v26.10.06.10 system.

THIS REVISION
-------------
1) W1P -> Leadshine operational Modbus now matches EL7-RS factory communication:
   38400 baud, 8N2, slave/axis ID 1 (P05.29=5, P05.30=4, P05.31=1).
   The old 115200/8N1 setting is retained only as a stopped/read-only diagnostic
   probe and cannot establish normal link authority.

2) The W1P motor holding-brake power switch is EdgeBox DO0. The Leadshine EL7
   still owns brake timing logically through configured DO4/BRK-OFF, which W1P
   reads over Modbus. The physical Leadshine DO4 terminal is not used for the coil.

EdgeBox brake wiring:
   pin 1 DO_24V = +24 V output-bank supply
   pin 3 DO_GND = 0 V output-bank supply
   pin 5 DO0    = motor-brake low-side switched return
   brake +      = same +24 V rail feeding pin 1

DO0 LOW/off = brake applied. DO0 HIGH/on = brake released.
The local W1P DI0 E-stop remains ACTIVE in this revision; there is no bypass.

3) The established updater remains ordered CTRL -> W1P -> CTRL-TS. CTRL and W1P
   authority-update phase/percentage is forwarded through SRVR/CTRL and rendered
   on the CTRL-TS update-status screen before the touchscreen's own final update.

See W1P_BRAKE_WIRING_v26.10.08.02.md and
NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.10.08.02.md before powered commissioning.

CTRL/CTRL-TS behavior, motion control, calibration, AUX, limits, firmware authority
and the v26.10.06.11 cable-marker smoothing path remain locked except for release
identity and SRVR's interpretation of BRAKE_DO0 telemetry.

GitHub Actions/native compilation and physical brake/EL7 bench commissioning remain
authoritative. No firmware binaries are included in this source package.
