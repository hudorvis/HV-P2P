# HV P2P v26.11.12.02 — native-build and physical commissioning checklist

**Not proof of completed field commissioning.** Record actual results when running GitHub Actions and the motor bench.

## GitHub Actions

- [ ] Commit the *contents* of the source ZIP to repository root including `.github/workflows/complete-build.yml`.
- [ ] Trigger `HV P2P Complete Build v26.11.12.02`; record the run URL, SHA, commit and artifacts.
- [ ] Confirm the firmware job runs on Ubuntu 24.04 x64 and resolves Python 3.12.10. Confirm the packaging job runs on Ubuntu 24.04.
- [ ] Confirm native ESP32 core 3.3.8 / Arduino CLI 1.5.1, compiled CTRL-TS image staged into CTRL, and CTRL, W1P and Olimex PDM images. Verify the authority hashes and release identities, including the PDM OTA partition check.
- [ ] Confirm macOS Intel/Apple Silicon and Windows x64 dependency pin, source and frozen smoke, QML lint, Nuitka and packaged autorun.
- [ ] Confirm `position_feedback.py` was included in frozen SRVR binaries; no module import errors on any platform.
- [ ] Verify GitHub release internal SHA-256 manifest and external ZIP checksum after native compilation.

## Hardware/bench gates

- [ ] Read motor nameplate/model and actual max rated RPM. Confirm MotionStudio RPM, electronic gear factor, 10,000 command units/revolution and winch `UPM` using a measured known distance.
- [ ] Verify RS485 UART 115200 8N1, Modbus ID 1, register read P08.44/45/46/47, word order, CRC, and actual drive feedback interval. Note the observed UDP `POS_SEQ`, `POS_T_MS`, `POS_AGE_MS`, `RAW_POS` and `RAW_POS_EXT` values.
- [ ] Mechanically isolate load/rope from personnel. Jog at 125 / 250 / 500 RPM then motor's verified rated maximum; compare physical measured travel with SRVR, CTRL-TS, Free-D and Leadshine counts.
- [ ] After Near slip, check 0–1000 m calibration, 1000+ m measured-travel reporting, reverse travel and allowed service-mode overshoot. Do **not** travel past installed physical limits to test software readouts: use an isolated encoder/drive simulation first.
- [ ] Inject invalid position jumps, late/duplicated/reordered UDP, unplugged RS485, W1P reboot and restored link; verify data freeze only when rejected, safety faults and reference re-arm requirement.
- [ ] Independently validate CTRL E-stop, W1P AI0 E-stop, EdgeBox DO0 24 V motor-brake release, EL7 DO2/SRDY, DO3/SRV-ST, DO4/BRK-OFF, DO5/ALARM, watchdog, drive soft limits and servo inhibit; confirm MotionStudio external control cannot bypass physical safety.
- [ ] Confirm firmware auto-update convergence in proper order (CTRL -> W1P -> CTRL-TS), optional HMI recovery, settings persistence and startup connection logs; review any mismatch before applying load.

## Physical Olimex PDM checks

- [ ] Back up the card and USB-bootstrap an existing PDM without erase. Confirm saved Ethernet/AP settings, labels, alarms, calibration, log interval and retained CSVs.
- [ ] Verify browser access on Ethernet and AP, and compare all four rails, timestamps and retained history with the SRVR Monitoring → PDM view while the device logs.
- [ ] On an isolated bench, perform an SRVR-driven update, observe idle gating and reconnect, and check retained settings, logs and both browser access paths afterwards.
- [ ] Disconnect Ethernet or interrupt power during staging, then retry. Confirm the previous application boots after interruption before activation and prove USB recovery with the original card.
- [ ] Repeat with PDM absent and during isolated winch operation. Verify the PDM update waits through motion and CTRL/W1P/CTRL-TS readiness and communication remain independent.

## Monitoring checks on devices

- [ ] Change Log Interval and Log Duration in SRVR and confirm the PDM dashboard shows the new values. Repeat from the dashboard, then reopen the SRVR dialog.
- [ ] Check the refreshed dashboard on desktop and iOS via Ethernet and the Wi-Fi AP. Verify voltage readings, calibration, history and CSV export.
- [ ] Once sensor firmware is available, configure the WSI at a separate address and compare live readings, history, hover values, the web shortcut and saved log settings across both interfaces.
