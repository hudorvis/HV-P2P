HV P2P v26.11.08.01
===================
Source release for GitHub Actions | 8 November 2026
Approved input package — HV P2P v26.10.19.01 ChatGPT.zip

The archive opens at the repository root. Replace the prior versioned source
folders with the four v26.11.08.01 component folders and include the root
.github/workflows/complete-build.yml, tools and documentation. Run the workflow
named HV P2P Complete Build v26.11.08.01.

The release fixes SRVR encoder timestamp rollback, W1P Modbus sample timing,
and W1P/SRVR RS485 startup diagnostics. It also corrects clock rollover in
CTRL and CTRL-TS, stale SRVR link leases after desktop clock changes, and
validation of joystick and calibration inputs.

Run python3 tools/run_all_source_checks.py with Python 3, g++ and PySide6 6.11.1
to include the SRVR backend runtime test. TEST_RESULTS_v26.11.08.01.txt and
SOURCE_REGRESSION_LOG_v26.11.08.01.txt record the verification. The source hashes
are in CHECKSUMS_SHA256.txt.

GitHub Actions provides the matching native firmware and desktop artifacts.
Use NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.11.08.01.md for the separate native
build and physical commissioning steps.
