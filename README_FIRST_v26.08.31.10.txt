HV P2P v26.08.31.10 — GITHUB-READY SOURCE RELEASE
====================================================

BASELINE
--------
v26.08.31.10 is the corrected build revision following the issued v26.08.31.09
source pack. It preserves the complete locked .09 Run/Setup revision and all
v26.08.31.07/.08 safety/build hardening unchanged. v26.08.31.06 remains the
authoritative historical pre-fix baseline.

The SRVR Run and Setup pages are LOCKED at the user-approved v26.08.31.09 design.
Do not redesign those pages or alter their control semantics unless specifically
requested. Free-D, Log and CTRL-TS operator layouts remain on their existing
approved design.

V26.08.31.10 BUILD CORRECTION
-----------------------------
The first issued .09 source pack reached GitHub's macOS SRVR runtime regression
and stopped before producing a compiled .09 release.

v26.08.31.10 contains only these two corrective changes on top of .09:
- entering Virtual now latches the local software Servo Enable safety inhibit even
  when smoke-test mode suppresses physical hardware writes;
- the Virtual motion regression explicitly establishes its own neutral joystick /
  calibration test state instead of inheriting earlier reversed test state.

No approved Run/Setup layout or control semantics changed in .10.

LOCKED RUN / SETUP DESIGN
-------------------------
Run:
- logo HV P2P / SRVR; separate HV P2P | SRVR heading removed;
- Save/Recall/Slip use one global five-second two-step confirmation;
- System direct-mode controls retain their original semantics;
- Mode 1/Mode 2 remain fully visible and aligned;
- TO NEAR / TO FAR units remain beside their values.

Setup:
- CTRL: CTRL IP / Link / RS485 / E-Stop / Firmware / Direction;
- W1P:  W1P IP / Link / RS485 / E-Stop / Firmware / Direction;
- identical CTRL/W1P row geometry and divider position;
- CTRL-TS Link uses green Active / red Disconnected status;
- Motion Profiles divider retains equal Mode 1 / Mode 2 spacing;
- Position Source options remain Encoder and Virtual.

VIRTUAL POSITION SOURCE
-----------------------
Virtual remains a safe SRVR-local demo source for using real CTRL/CTRL-TS input
without driving the physical winch:
- non-zero W1P VEL is never transmitted;
- any available W1P is held with STOP and SW_SRVON 0 when real I/O is enabled;
- local position/speed are simulated through normal profile/limit logic;
- physical W1P telemetry cannot overwrite the simulation;
- Virtual Slip/re-reference does not send physical SYNC_POS;
- returning to Encoder requires the normal neutral/re-arm path.

INHERITED SAFETY/BUILD FIXES
----------------------------
- independent 650 ms W1P VEL deadman;
- fail-closed W1P OTA/reboot/reset service gate;
- firmware content-role OTA validation;
- pinned Waveshare_ST7262_LVGL commit
  593775b89ebfd2d411df3eadba7bc382767ed4a4;
- transactional W1P IP readdress with rollback;
- atomic/recoverable SRVR config persistence;
- Free-D u24 output + D1 checksum fixes;
- stable macOS bundle metadata;
- protected Complete Release / nested SRVR ZIP packaging and SHA-256 manifests.

SOURCE VALIDATION
-----------------
Integrated source validation: 316 checks PASS.
Build-pipeline validation: 34 checks PASS.
Full tools/run_all_source_checks.py: PASS.

The real PySide6 runtime backend suite and native Arduino builds are performed by
GitHub Actions.

GITHUB BUILD
------------
Upload the contents of this ZIP at repository root and run:
  .github/workflows/complete-build.yml

The workflow must produce the matched v26.08.31.10 CTRL-TS, CTRL and W1P native
firmware, freeze/smoke-test the Intel macOS SRVR app, preserve the original nested
SRVR ZIP, and package the v26.08.31.10 Complete Release.

Do not treat a successful compile as powered-motion commissioning approval. Use
NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.08.31.10.md before hardware sign-off.
