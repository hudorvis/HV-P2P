# HV P2P v26.10.06.04 native-build and bench checklist

## GitHub gate

1. Upload the complete `.06.04` source to the repository.
2. Confirm CTRL-TS, CTRL and W1P native compilation succeeds.
3. Confirm macOS Intel, macOS Apple Silicon and Windows SRVR source/runtime/frozen tests pass.
4. Confirm the matched release artifact contains `.06.04` SRVR and firmware outputs.

## Automatic-update bench test

Start with CTRL/W1P/CTRL-TS on the previous release and the system stationary/safe.

1. Launch `.06.04` SRVR and do not manually reboot any node.
2. Confirm CTRL starts release discovery automatically. A W1P/CTRL-TS coordinator problem must no longer suppress the CTRL release beacon.
3. Confirm CTRL reports `.06.04` and exact authority match after its reboot.
4. Confirm W1P receives the preferred second-stage update attempt.
5. Confirm the older CTRL-TS is still visible as physical RS485/Link **Active** during a version mismatch instead of falsely reading Disconnected.
6. Confirm CTRL-TS begins automatically after the normal SRVR grant. If that grant path remains unavailable, confirm the CTRL-local 12 s recovery begins the approved safe-OTA final stage without a manual reboot.
7. Confirm CTRL-TS goes black only while flashing its own inactive partition, verifies size/SHA, reboots itself and returns on `.06.04`.
8. Confirm no node requires a manual reboot to discover the release.

## Safety regression

- W1P independent VEL watchdog remains 500 ms.
- SRVR non-zero VEL refresh remains approximately 150 ms.
- AI0 E-stop / AI1 joystick mapping unchanged.
- Predictive/dynamic and hard limits unchanged.
- Leadshine velocity/Modbus architecture unchanged.
- Limit Calibration and joystick-neutral interlock unchanged.
