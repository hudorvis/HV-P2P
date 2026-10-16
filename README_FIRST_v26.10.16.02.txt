HV P2P v26.10.16.02 — GitHub-ready coordinated source release
=============================================================
Release date: 16 October 2026. Locked baseline: v26.10.16.01.

CHANGED THIS REVISION: SRVR Log now includes a startup discovery summary and
state-change-only connection reports for CTRL UDP, W1P UDP, Leadshine EL7
RS485 Modbus, CTRL-TS, CTRL joystick AI1, firmware match and optional Free-D.
Brief outages are debounced, recovery logged promptly. RS485 Active means
valid EL7 Modbus communication, NOT readiness for motion.

UNCHANGED: All safety/motion/calibration/limit/AUX/updater/DO0 brake/E-stop
behavior, firmware authority, controller HMI and all QML pages. The embedded
node source is changed only for coordinated release identity.

See CHANGE_SUMMARY, DEEP_CODE_AUDIT and NATIVE_BUILD_AND_BENCH_CHECKLIST.

GITHUB UPLOAD: unzip and commit the entire contents (including hidden
.github/workflows/complete-build.yml) at the repository root. Do not upload
only the SRVR_GitHub folder. GitHub Actions must compile ESP32 firmware and
macOS Intel/Apple Silicon + Windows SRVR, then pass all native smoke tests.

The source package does NOT include production firmware binaries. Do not
assume powered motion-safe operation from source tests alone; verify the
Leadshine communication, hardware E-stops and 24 V brake on the bench.
