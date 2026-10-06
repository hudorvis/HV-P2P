# HV P2P v26.10.06.07 native-build and bench checklist

## GitHub gates

1. Upload the complete `.06.07` source tree.
2. Confirm CTRL-TS, CTRL and W1P native compilation succeeds.
3. Confirm macOS Intel, macOS Apple Silicon and Windows SRVR jobs pass.
4. Confirm the matched release artifact contains `.06.07` SRVR and firmware outputs.

## Automatic-update bench test

Start with CTRL and CTRL-TS on the previous release and do **not** manually reboot either unit.

Expected sequence:

1. CTRL heartbeat connects to SRVR.
2. CTRL receives the `.06.07` release either from the normal background beacon or the redundant heartbeat-return beacon.
3. CTRL enters authority update automatically and CTRL-TS displays CTRL progress.
4. CTRL reboots into `.06.07`; any lost final CTRL progress status self-clears when the new CTRL sends HELLO.
5. If CTRL-TS is still old, normal coordinator grant starts its update. If that grant was lost, the CTRL-local approved-target fallback begins after 12 seconds without requiring an SRVR session token.
6. CTRL-TS performs the existing display-off/headless verified update and autonomously reboots into `.06.07`.

## SRVR-close / splash test

1. Run SRVR until CTRL and CTRL-TS are fully connected and Home is stable.
2. Close SRVR normally.
3. CTRL-TS must transition to the resident Waiting splash and remain there continuously.
4. It must not flash back to Home because of stale HMI packets or firmware-screen release.
5. Restart SRVR; CTRL POLL `srvr=1` and fresh HMI state should restore Home normally.

## Locked safety checks

- W1P independent VEL watchdog remains 500 ms.
- Normal SRVR non-zero VEL refresh remains approximately 150 ms.
- AI0 E-stop / AI1 joystick mapping unchanged.
- Predictive/dynamic/hard limits unchanged.
- Leadshine velocity/Modbus architecture unchanged.
- Calibration transactions and Cancel behavior unchanged.
- `.06.05` two-tap confirmation and status states unchanged.
