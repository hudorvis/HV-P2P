HV P2P v26.10.08.05 - GitHub Ready Source
================================================
Source baseline: v26.10.08.04.

THIS REVISION
-------------
1) Fixes the macOS Intel frozen-SRVR startup crash introduced by the new .08.04
   Leadshine/RS485 log path. The crash report points to the Qt main timer entering
   the unchanged DSP1 builder immediately after the new diagnostic path.

2) Keeps the same useful [W1P RS485] fault/recovery messages, but reduces them to
   plain data first and defers the Qt log signal until after DSP1 construction.

3) Extends the frozen-app smoke test so both macOS architectures must execute the
   exact diagnostic -> repeated DSP1-build sequence before a release can publish.

PRESERVED FROM v26.10.08.04
---------------------------
- W1P <-> EL7: 115200 baud / 8N1 / slave ID 1.
- EL7 settings: P05.29=4, P05.30=6, P05.31=1.
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

See W1P_ESTOP_WIRING_v26.10.08.05.md,
W1P_BRAKE_WIRING_v26.10.08.05.md and
NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.10.08.05.md before powered commissioning.

No firmware binaries are included in this source package. Native Arduino compilation
and frozen desktop/PySide runtime verification remain the GitHub Actions gates.
