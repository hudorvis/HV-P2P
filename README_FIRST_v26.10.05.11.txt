HV P2P v26.10.05.11 - READ THIS FIRST

PRIMARY PURPOSE OF THIS REVISION
--------------------------------
Fix the .05.10 bench regression where opening a newer SRVR could leave firmware
updates apparently idle until CTRL was manually rebooted, while CTRL-TS could
remain on the older release.

EXACT ROOT CAUSE
----------------
SRVR_ALIVE had already been moved to a background network worker so macOS/QML
scheduling could not falsely disconnect CTRL. Firmware discovery was still split:
SRVR_FW, the W1P release beacon and the CTRL-TS `ts_allowed` coordinator grant
were emitted only by the 25 ms Qt timer.

That meant CTRL could remain visibly connected while never learning that a new
SRVR release existed if the Qt event loop was delayed. A manual CTRL reboot then
worked because boot-time manifest discovery is independent of Qt. CTRL-TS could
stay old because its final coordinator grant was also Qt-dependent.

WHAT .05.11 CHANGES
-------------------
1. Background firmware convergence
   - The background SRVR communications worker now emits both SRVR_ALIVE and the
     lightweight firmware/coordinator beacons.
   - Firmware release discovery no longer depends on window focus/QML/Qt timer.
   - HTTP/flash and motion decisions remain outside this worker.

2. CTRL -> W1P -> CTRL-TS order
   - W1P firmware/version/match state and OTA FW_PROGRESS are captured directly
     in its UDP receive thread for update ordering, including while normal STATUS
     pauses during the blocking image download.
   - A healthy W1P gets a bounded 3-second discovery grace after CTRL converges.
   - A W1P already participating in the release holds CTRL-TS through its OTA
     reboot; a 15-second bounded absence escape prevents a dead/absent W1P from
     stranding the display forever.

3. New SRVR authority-session revalidation
   - CTRL and W1P now treat a new SRVR process/session as an authority boundary.
   - They re-check the immutable manifest and running SHA even if the human-readable
     version is unchanged.
   - An already exact image is accepted without reflashing.

4. Graceful shutdown race closed
   - CTRL firmware beacons re-check shutdown while holding the same TX lock used
     by SRVR_OFFLINE, so no late worker packet can resurrect a closed SRVR session.

PRESERVED FROM .05.10
---------------------
- Limit Calibration display re-zeros to staged Near and shows travel toward Far.
- Run > Shortcuts > System controls fit correctly inside their panel.
- `Drive Mode | Practice Mode` reaches CTRL-TS without source-side truncation.

PRESERVED SAFETY / CONTROL CONTRACTS
------------------------------------
- W1P independent 500 ms VEL freshness watchdog is unchanged.
- Normal SRVR non-zero VEL refresh remains approximately 150 ms.
- AI0 E-stop / AI1 joystick mapping is unchanged.
- Joystick-neutral re-arm remains required after a genuine safety stop.
- Leadshine velocity architecture, hard limits and predictive/dynamic limits are
  unchanged.
- CTRL <-> CTRL-TS RS485 remains isolated half-duplex single-flight/serialized
  with EVENT ACK/retry handling.
- CTRL-TS safe self-update remains black/headless while writing its own flash.
- REBOOT ACK is not update completion; post-reboot exact identity is required.

VERIFICATION STATUS
-------------------
Complete source/static/regression/preflight suite passes locally, including 370
EdgeBox integration checks, all previous bench regressions, the new .05.11
background firmware convergence test, 53 build-pipeline checks, release/source
hygiene, Python syntax and SRVR preflight.

PySide6 is not installed in this source-audit environment. Native Arduino firmware
compilation and frozen desktop/PySide smoke tests remain authoritative GitHub
Actions gates. Physical automatic-update/RS485/Leadshine behavior remains a bench
gate. No locally fabricated firmware binaries are included.

FIRST BENCH TEST
----------------
Start with older supported firmware on CTRL/W1P/CTRL-TS. Launch the GitHub-built
.05.11 SRVR and DO NOT manually reboot any ESP32. The required result is automatic
CTRL -> W1P -> CTRL-TS convergence, with CTRL-TS autonomously rebooting from its
black headless updater into the .05.11 application.
