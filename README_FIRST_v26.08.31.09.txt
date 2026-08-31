HV P2P v26.08.31.09 — GITHUB-READY SOURCE RELEASE
====================================================

BASELINE
--------
v26.08.31.09 is based directly on v26.08.31.08 and retains all audit fixes from
v26.08.31.07/.08. v26.08.31.06 remains the authoritative historical pre-fix
baseline.

The SRVR Run and Setup pages are intentionally revised and LOCKED by the user in
this release. Do not redesign those pages or alter their control semantics unless
specifically requested. Free-D, Log and CTRL-TS operator layouts remain on their
existing approved design.

LOCKED RUN CHANGES
------------------
- Logo: HV P2P / SRVR; separate HV P2P | SRVR heading removed.
- Run Shortcut Save/Recall/Slip actions use one global five-second two-step
  confirmation. First press -> Confirm? 5s; second press executes. Timeout or a
  different/immediate action cancels the previous pending confirmation.
- Preset editing/visibility and System direct-mode controls retain their original
  semantics.
- System Mode 1/Mode 2 labels are fully visible and all first action controls use
  a common left alignment.
- TO NEAR / TO FAR metre units remain adjacent to their values.

LOCKED SETUP CHANGES
--------------------
CTRL diagnostic rows:
  CTRL IP / Link / RS485 / E-Stop / Firmware / Direction
W1P diagnostic rows:
  W1P IP / Link / RS485 / E-Stop / Firmware / Direction

The two panels use identical six-row vertical geometry and divider height. CTRL
RS485 is the CTRL-TS RS485 link; W1P RS485 is the EL7 RS485 link. CTRL/W1P actual
firmware versions are published by firmware and displayed by SRVR.

The CTRL-TS panel is now:
  CTRL-TS Link
  ----------------
  Detected
  Required
  Update
CTRL-TS Link is green Active / red Disconnected, matching the other link status
rows.

Motion Profiles data/layout is unchanged except for equal clearance around the
Mode 1 / Mode 2 centre divider.

VIRTUAL POSITION SOURCE
-----------------------
Setup Position Source options are Encoder and Virtual. Virtual is a safe SRVR-only
demo source for using real CTRL/CTRL-TS input without driving the winch:
- non-zero W1P VEL is never transmitted;
- any available W1P is positively held with STOP and SW_SRVON 0;
- position/speed are simulated locally through the normal motion/profile/limit
  logic;
- physical W1P position/speed cannot overwrite the simulation;
- Virtual Slip/re-reference does not send physical SYNC_POS;
- W1P/EL7 link state is not required for Virtual demo operation;
- returning to Encoder requires the normal neutral/re-arm path before physical
  Servo Enable is restored.

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

The PySide6 runtime backend suite is run by the GitHub macOS job after installing
the pinned requirements. PySide6 is not installed in the preparation container,
so it was not falsely reported as a local pass. Native Arduino compilation is
also performed by the GitHub workflow.

GITHUB BUILD
------------
Upload the contents of this ZIP at repository root and run:
  .github/workflows/complete-build.yml

The workflow must produce the matched v26.08.31.09 CTRL-TS, CTRL and W1P native
firmware, freeze/smoke-test the Intel macOS SRVR app, preserve the original nested
SRVR ZIP, and package the v26.08.31.09 Complete Release.

Do not treat a successful compile as powered-motion commissioning approval. Use
NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.08.31.09.md before hardware sign-off.
