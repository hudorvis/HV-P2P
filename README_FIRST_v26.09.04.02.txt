HV P2P v26.09.04.02 — GITHUB-READY SOURCE RELEASE
====================================================

WINDOWS CI BUILD CORRECTION
---------------------------
v26.09.04.02 supersedes v26.09.04.01 after the first Windows x64 GitHub build
stopped inside Nuitka before producing an executable. The application/firmware
behaviour and locked Run/Setup UI are unchanged. Windows CI now initializes the
x64 MSVC developer environment, proves dumpbin is available, pins Nuitka 4.2,
and forces required Nuitka tool downloads non-interactively with
--assume-yes-for-downloads.

The earlier v26.08.31.11 package remains a withdrawn wrongly dated draft
designation; v26.09.04.01 was the first correctly dated source revision but did
not produce an authoritative complete release.

BASELINE
--------
v26.09.04.02 is functionally based on v26.09.04.01 (itself based on the corrected v26.08.31.10 source). It preserves
all v26.08.31.07/.08 safety/build hardening and the locked v26.08.31.09 Run/Setup
operator design and Virtual Position Source behavior.

The SRVR Run and Setup pages remain LOCKED. Do not redesign those pages or alter
their control semantics unless specifically requested. Free-D, Log and CTRL-TS
operator layouts also remain unchanged in this revision.

V26.09.04.02 MOTION-CONTROL AUDIT
---------------------------------
No Power/Speed motion behavior is retuned in this revision.

Speed:
- SRVR maps Speed to W1P SET_ACCEL_MODE DYNAMIC.
- W1P uses measured cable-speed feedback with bounded proportional + integral
  correction around the commanded speed profile.
- The EL7 remains in PR0 velocity mode; its internal servo loop supplies the
  torque/current required to maintain the corrected velocity target.
- Under-speed raises the commanded velocity correction; over-speed lowers it.
- Correction is bounded, cannot reverse the requested direction, and its integral
  is reset at zero/no target.

Power:
- SRVR maps Power to W1P TRADITIONAL.
- It remains the established traditional/direct velocity-profile response without
  the W1P outer speed-hold correction.
- It is NOT changed into torque mode or a direct watts/current command.

A dedicated source regression, tools/test_speed_mode_contract.py, now locks these
semantics. Physical load testing is still required during commissioning.

CROSS-PLATFORM SRVR
-------------------
The next GitHub build now produces and verifies three native SRVR applications:
- macOS Intel / x86_64;
- macOS Apple Silicon / arm64;
- Windows x64 / AMD64.

The SRVR configuration directory is native per OS. Windows FileDialog drive-letter
and UNC URLs are also normalized correctly.

COMPLETE RELEASE
----------------
The workflow must produce matched native firmware plus these untouched nested SRVR
archives:
- HV P2P SRVR v26.09.04.02 macOS Intel.zip
- HV P2P SRVR v26.09.04.02 macOS Apple Silicon.zip
- HV P2P SRVR v26.09.04.02 Windows x64.zip

The Complete Release is not created unless firmware and all three SRVR native
builds pass. Internal SHA256SUMS.txt and the external Complete Release .sha256 are
retained.

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
- versioned macOS bundle metadata;
- protected Complete Release / nested SRVR ZIP packaging and SHA-256 manifests.

SOURCE VALIDATION
-----------------
Integrated source validation: 316 checks PASS.
Build-pipeline validation: 44 checks PASS.
Speed-mode control contract: PASS.
Full tools/run_all_source_checks.py: PASS.
Backend runtime regression: PASS with the local QtCore compatibility harness.

The real pinned PySide6 runtime regression executes again on all three native SRVR
GitHub runners, and native Arduino builds execute on the firmware runner.

GITHUB BUILD
------------
Upload the contents of this ZIP at repository root and run:
  .github/workflows/complete-build.yml

Do not treat a successful compile as powered-motion commissioning approval. Use
NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.09.04.02.md before hardware sign-off.
