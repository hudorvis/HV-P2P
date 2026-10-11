HV P2P v26.10.11.01 - GitHub Ready Source
================================================
Source baseline: v26.10.08.05.

THIS REVISION
-------------
1) Corrects the release date/build line to 2026-10-11.

2) Addresses the GitHub macOS Intel native crash exposed by v26.10.08.05:
   packaging/signing completed, but the frozen app exited SIGSEGV/139 during
   --smoke-test. The log also showed pyside6-deploy silently installing Nuitka 4.3.

3) Makes desktop builds deterministic:
   Python 3.12.10
   PySide6 6.11.1
   Nuitka 4.2.2
   CI verifies Nuitka before/after pyside6-deploy so it cannot silently change.

4) Removes nested functions/lambdas from SRVR backend runtime paths, including the
   DSP1/calibration helpers implicated by the earlier native CALL_FUNCTION crash
   family. Behaviour and on-wire data are preserved.

5) Strengthens the frozen-app smoke test to 200 diagnostic -> DSP1 iterations,
   adds phase markers/faulthandler, and prints the latest Apple crash report if a
   native macOS failure recurs. The post-ZIP smoke has the same crash capture.

6) Isolates all --smoke-test config writes in a private temporary directory. Smoke
   runs cannot overwrite the operator's Application Support config or contaminate
   later CI smoke stages.

PRESERVED FROM v26.10.08.05
---------------------------
- W1P <-> EL7: 115200 baud / 8N1 / slave ID 1.
- EL7 settings: P05.29=4, P05.30=6, P05.31=1.
- W1P local E-stop: AI0 / 5 V fail-closed status loop.
- EdgeBox DO0 directly switches the 24 V spring-applied motor brake; LOW/off applies
  the brake and HIGH/on releases it under verified EL7 BRK-OFF sequencing.
- CTRL -> W1P -> CTRL-TS automatic update order and update progress screen.
- CTRL-TS real-position marker smoothing.
- Motion, limits, calibration, AUX, watchdog, firmware-authority and UI behavior.

W1P AI0 wiring on the commissioned connector:
  pin 14 AI0 = +5 V through the normally-closed E-stop contact
  pin 12 AGND = 5 V supply 0 V

IMPORTANT AI0 HARDWARE REQUIREMENT
----------------------------------
The W1P 5 V E-stop input assumes AI0 is configured for voltage input like the
commissioned CTRL EdgeBox (factory 249-ohm current shunt removed, or 0-10 V input
hardware option). Use AGND for the analogue return.

See W1P_ESTOP_WIRING_v26.10.11.01.md,
W1P_BRAKE_WIRING_v26.10.11.01.md and
NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.10.11.01.md before powered commissioning.

No firmware binaries are included in this source package. Native Arduino compilation
and actual frozen desktop/PySide runtime verification remain GitHub Actions gates.
