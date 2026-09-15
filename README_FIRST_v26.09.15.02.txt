HV P2P v26.09.15.02 — GITHUB-READY SOURCE
==========================================

PURPOSE
-------
This is the clean corrective source revision for the v26.09.14.03 frozen-SRVR
firmware-resource failure.

The authority chain remains:

  SRVR -> Ethernet OTA -> CTRL -> RS485 OTA -> CTRL-TS
       -> Ethernet OTA -> W1P

WHAT CHANGED
------------
The v26.09.14.03 native SRVR executables were created correctly but their frozen
payloads omitted ctrl.bin/w1p.bin because Nuitka treats *.bin as binary/code and
skips it from ordinary --include-data-dir handling.

v26.09.15.02 force-includes the exact CTRL/W1P images with explicit
--include-data-files rules, verifies them in the completed macOS app/release ZIP,
and retains the Windows frozen-runtime smoke test. A shared spec patcher is used
by both operating-system paths.

The source ZIP itself is also cleaned: no old preview/reference screenshots,
superseded change-audit files, old revision-specific summaries, generated native
outputs or cache directories are included. Source-package hygiene is now tested.

LOCKED / PRESERVED
------------------
- Run and Setup QML remain byte-identical to the approved baseline.
- Speed = established W1P DYNAMIC cable-speed PI.
- Power = established TRADITIONAL behavior.
- W1P independent 650 ms VEL watchdog preserved.
- W1P stopped/braked OTA gate, Servo Enable inhibit, brake/E-stop/RS485 protections
  and rollback/recovery preserved.
- Missing/false FW_MATCH remains fail-closed.
- A newer EdgeBox is never automatically downgraded.
- CTRL must match SRVR before CTRL->CTRL-TS update logic may proceed.

BUILD
-----
Upload/extract this source as the GitHub repository content and run the complete
GitHub Actions workflow. The authoritative build order is:

  CTRL-TS -> embed exact CTRL-TS -> CTRL -> W1P -> verify immutable firmware bundle
  -> macOS Intel SRVR -> macOS Apple Silicon SRVR -> Windows x64 SRVR
  -> Complete Release

LOCAL SOURCE VALIDATION
-----------------------
Run:

  python3 tools/run_all_source_checks.py

Native .bin/.app/.exe outputs are intentionally not present in this source ZIP.
GitHub Actions remains the native compile/frozen-runtime authority.

BOOTSTRAP / BENCH
-----------------
Read:
- INITIAL_BOOTSTRAP_v26.09.15.02.md
- NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.09.15.02.md
