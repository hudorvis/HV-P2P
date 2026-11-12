# HV P2P v26.11.12.09 — native-build and physical commissioning checklist

**Not proof of completed field commissioning.** Record actual results when running GitHub Actions and the motor bench.

## GitHub Actions

- [ ] Commit the *contents* of the source ZIP to repository root including `.github/workflows/complete-build.yml`.
- [ ] Trigger `HV P2P Complete Build v26.11.12.09`; record the run URL, SHA, commit and artifacts.
- [ ] Confirm the firmware job runs on Ubuntu 24.04 x64 and resolves Python 3.12.10. Confirm the packaging job runs on Ubuntu 24.04.
- [ ] Confirm native ESP32 core 3.3.8 / Arduino CLI 1.5.1, compiled CTRL-TS image staged into CTRL, and CTRL, W1P and Olimex PDM images. Verify the authority hashes and release identities, including the PDM OTA partition check.
- [ ] Confirm macOS Intel/Apple Silicon and Windows x64 dependency pin, source and frozen smoke, QML lint, Nuitka and packaged autorun.
- [ ] Confirm `position_feedback.py` was included in frozen SRVR binaries; no module import errors on any platform.
- [ ] Verify GitHub release internal SHA-256 manifest and external ZIP checksum after native compilation.

On the Intel Mac, confirm SRVR opens with AirPlay Receiver active on TCP 5000. Verify a conflict on TCP 5760 names the port and Retry recovers after it is freed.

## Hardware/bench gates

- [ ] Read motor nameplate/model and actual max rated RPM. Confirm MotionStudio RPM, electronic gear factor, 10,000 command units/revolution and winch `UPM` using a measured known distance.
- [ ] Verify RS485 UART 115200 8N1, Modbus ID 1, register read P08.44/45/46/47, word order, CRC, and actual drive feedback interval. Note the observed UDP `POS_SEQ`, `POS_T_MS`, `POS_AGE_MS`, `RAW_POS` and `RAW_POS_EXT` values.
- [ ] Mechanically isolate load/rope from personnel. Jog at 125 / 250 / 500 RPM then motor's verified rated maximum; compare physical measured travel with SRVR, CTRL-TS, Free-D and Leadshine counts.
- [ ] After Near slip, check 0–1000 m calibration, 1000+ m measured-travel reporting, reverse travel and allowed service-mode overshoot. Do **not** travel past installed physical limits to test software readouts: use an isolated encoder/drive simulation first.
- [ ] Inject invalid position jumps, late/duplicated/reordered UDP, unplugged RS485, W1P reboot and restored link; verify data freeze only when rejected, safety faults and reference re-arm requirement.
- [ ] Independently validate CTRL E-stop, W1P AI0 E-stop, EdgeBox DO0 24 V motor-brake release, EL7 DO2/SRDY, DO3/SRV-ST, DO4/BRK-OFF, DO5/ALARM, watchdog, drive soft limits and servo inhibit; confirm MotionStudio external control cannot bypass physical safety.
- [ ] Cold-start an older W1P before CTRL has verified the new release. Confirm W1P starts downloading only after CTRL verifies the exact bundle, then confirm CTRL-TS installs and reports the new boot identity. Check startup connection logs, persisted settings and the optional HMI recovery case before applying load.
- [ ] Interrupt an EdgeBox download during an isolated service test. Confirm its progress clears, it retries or recovers via the approved fallback and it verifies the exact release after reboot.

## Physical Olimex PDM checks

- [ ] Back up the card and USB-bootstrap an existing PDM without erase. Confirm saved Ethernet/AP settings, labels, alarms, calibration, log interval and retained CSVs.
- [ ] Open the PDM in a browser using just the Ethernet or AP IP. Compare all four rails, timestamps and retained history with the SRVR Monitoring → PDM view while the device logs.
- [ ] On an isolated bench, perform an SRVR-driven update, observe idle gating and reconnect, and check retained settings, logs and both browser access paths afterwards.
- [ ] Disconnect Ethernet or interrupt power during staging, then retry. Confirm the previous application boots after interruption before activation and prove USB recovery with the original card.
- [ ] Repeat with PDM absent and during isolated winch operation. Verify the PDM update waits through motion and CTRL/W1P/CTRL-TS readiness and communication remain independent.

## Monitoring checks on devices

- [ ] Open Monitoring → PDM → Settings while offline and apply the correct Ethernet address. Once connected, change Log Interval and Log Duration and confirm the PDM dashboard shows the new values. Repeat from the dashboard, then reopen the SRVR dialog.
- [ ] Check the refreshed dashboard on desktop and iOS via Ethernet and the Wi-Fi AP. Verify voltage readings, calibration, history and CSV export.
- [ ] Once sensor firmware is available, configure the WSI at a separate address and compare live readings, history, hover values, the web shortcut and saved log settings across both interfaces.

- [ ] With a v26.11.09.04 PDM running, verify its manifest request reaches SRVR on TCP 5088. After safe-idle OTA, verify the dashboard and SRVR monitoring reconnect on TCP 80 and the PDM's new manifest request reaches SRVR on TCP 5760.
- [ ] With a v26.11.12.07 or .08 PDM, follow the manifest, permit and image requests in the new SRVR Log. Check that an unavailable safe-idle window holds the update and that the PDM reports v26.11.12.09 after a verified download and reboot.
- [ ] Verify CTRL/W1P migrate using the legacy authority listener, then request the manifest on TCP 5760. Check that control UDP 5760 and CTRL-TS RS485 operate on the commissioned setup.
- [ ] Compare Live, Min and Max with the PDM web dashboard. Change alarms without changing calibration. Enter a measured Actual Voltage and verify the stored offset from both interfaces.
