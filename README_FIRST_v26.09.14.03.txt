HV P2P v26.09.14.03 — GITHUB-READY SOURCE
==========================================

SRVR-AUTHORITATIVE FIRMWARE CONVERGENCE + DEEP CI/SAFETY AUDIT
----------------------------------------------------------------
This revision carries forward the v26.09.14.01 authority chain, retains the v26.09.14.02
Arduino `HEX_DIGITS` compile correction, fixes the cross-platform backend regression
fixture, and adds fail-closed protection against stale/malformed W1P STATUS state.

Authority chain:

  SRVR -> Ethernet OTA -> CTRL -> RS485 OTA -> CTRL-TS
       -> Ethernet OTA -> W1P

After one authority-aware bootstrap install, CTRL and W1P compare their installed
release and exact running-image SHA-256 with the immutable firmware bundle carried
inside the matching SRVR build. Older or same-version/mismatched images are repaired
only through validated role-specific OTA. A newer EdgeBox is NEVER automatically
downgraded.

W1P automatic OTA reuses the existing stopped/braked service gate and preserves the
independent 650 ms VEL watchdog, Servo Enable inhibition, E-stop handling, drive-write
lockout and recovery/re-arm behavior. CTRL must exactly match SRVR before its existing
CTRL->CTRL-TS version/hash updater is allowed to run.

LOCKED / PRESERVED
------------------
- Approved Run tab: byte-identical to v26.09.04.03.
- Approved Setup tab: byte-identical to v26.09.04.03.
- Speed mode: unchanged W1P DYNAMIC cable-speed PI architecture.
- Power mode: unchanged TRADITIONAL behavior.
- Virtual mode: real W1P non-zero output remains inhibited.
- Windows x64 fixes from v26.09.04.03 retained: MSVC x64 environment, real PE
  dumpbin probe, Nuitka 4.2, --assume-yes-for-downloads, AMD64 check and frozen smoke.

BUILD ORDER / RELEASE INTEGRITY
-------------------------------
GitHub Actions builds CTRL-TS first, embeds that exact image into CTRL, builds CTRL,
builds W1P, verifies the resulting application identities/sizes/SHA-256 values, and
creates one immutable SRVR_FIRMWARE_BUNDLE. Mac Intel, Mac Apple Silicon and Windows
x64 SRVR jobs all depend on that firmware job and package that exact same bundle.
The Complete Release is gated on firmware plus all three native SRVR builds.

ONE-TIME BOOTSTRAP
------------------
Read INITIAL_BOOTSTRAP_v26.09.14.03.md before commissioning. USB/full-device flashing
is the bootstrap/recovery path; individual EdgeBox browser OTA remains a service
fallback for correctly partitioned devices. Future routine CTRL/W1P updates are
intended to converge from SRVR during stopped start-up/service windows.

SOURCE VALIDATION
-----------------
Run: python3 tools/run_all_source_checks.py

The master suite now includes a Qt-independent execution of the backend regression
logic and a release-path consistency gate, so shared backend/revision mistakes are
caught before Arduino setup/native build fan-out. Native SRVR jobs still repeat the
backend tests with the real pinned PySide6 runtime.

The final packaged source records the exact pass output in
SOURCE_TEST_RESULTS_v26.09.14.03.txt and authenticates every source file with
CHECKSUMS_SHA256.txt.

NATIVE OUTPUT POLICY
--------------------
This source pack does not invent native .bin, .app or .exe outputs. GitHub Actions is
the authoritative native compile/frozen-runtime gate. A successful native build is
still not powered-motion commissioning approval.
