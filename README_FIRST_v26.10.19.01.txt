HV P2P v26.10.19.01 — GitHub-ready, source-tested candidate
=============================================================
19 October 2026 | Locked, previously tested source baseline: v26.10.16.02

WHY THIS RELEASE:
SRVR stopped accepting genuine Leadshine position changes at higher speeds
because its telemetry-only filter used a 0.35 m step while SRVR was not
commanding motion. It also discarded measured positions beyond a +/-0.5 m
Near/Far tolerance. W1P signed-32-bit encoder rollover also lacked extended
count tracking and sample metadata.

FIX:
SRVR now tests position against the physical encoder's possible change in
its actual Modbus sample interval (not SRVR's last command). It retains raw
out-of-range measured positions for signed operator readouts without changing
independent motion-command limits. W1P now publishes POS_SEQ / POS_T_MS /
POS_AGE_MS / RAW_POS_EXT, counts rollover in both directions and computes
position in extended precision. Calibration reads validated extended counts.

UNCHANGED:
Existing approved UI layout, Free-D geometry, CTRL/CTRL-TS runtime,
RS485 configuration, SRVR motor-control limits, W1P motor command ceiling,
E-stop, 24 V brake DO0, watchdogs, firmware-update architecture and
startup connection logging. CTRL/CTRL-TS firmware only receives coordinated
release identity changes mandated by existing firmware-authority controls.

GITHUB:
Unzip and COMMIT THE CONTENTS of the top-level directory at repository root,
including hidden .github/workflows/complete-build.yml. GitHub Actions must
compile CTRL-TS -> embedded CTRL -> W1P firmware and macOS/Windows SRVR; this
source ZIP contains NO production firmware/application binaries.

CHECKS:
Read TEST_RESULTS_v26.10.19.01.txt for actual test results and limitations;
see DEEP_CODE_AUDIT_v26.10.19.01.md for the root-cause investigation.
Use `python3 tools/run_all_source_checks.py` for repeatable host checks.
Native ESP32, frozen Qt builds, and physical EL7/Modbus/motor tests are NOT
verified by a source-only package. Do not move a load until independent
E-stops, brake, all soft limits, and maximum motor RPM have been bench-tested.
