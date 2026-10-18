# HV P2P v26.10.19.01 — native-build and physical commissioning checklist

**Not proof of completed field commissioning.** Record actual results when running GitHub Actions and the motor bench.

## GitHub Actions

- [ ] Commit the *contents* of the source ZIP to repository root including `.github/workflows/complete-build.yml`.
- [ ] Trigger `HV P2P Complete Build v26.10.19.01`; record the run URL, SHA, commit and artifacts.
- [ ] Confirm native ESP32 core 3.3.8 / Arduino CLI 1.5.1, compiled CTRL-TS image staged into CTRL, CTRL and W1P native binaries, firmware authority hash and version match.
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
