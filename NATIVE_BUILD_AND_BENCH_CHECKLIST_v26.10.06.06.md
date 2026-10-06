# HV P2P v26.10.06.06 native-build and bench checklist

## GitHub gate

1. Upload the complete `.06.06` source to the repository.
2. Confirm the macOS/Windows PySide runtime step now gets past the previous `System | Active` assertion in `tools.test_backend_logic`.
3. Confirm CTRL-TS, CTRL and W1P native compilation succeeds.
4. Confirm macOS Intel, macOS Apple Silicon and Windows SRVR source/runtime/frozen tests pass.
5. Confirm the matched release artifact contains `.06.06` SRVR and firmware outputs.

## Runtime regression checkpoint

The fixed test must evaluate `System | Active` only from an explicit healthy stationary mid-span state:

- Near = 0.0 m;
- Far = 100.0 m;
- Current Position = 50.0 m;
- Current Speed = 0.0 m/s;
- last signed VEL = 0.0 m/s.

The subsequent `.06.05` assertions must still verify Near Limit, Far Limit and Ramping independently.

## Bench behavior

No production behavior intentionally changes from `.06.05`; normal `.06.05` bench validation remains applicable. In particular:

- every calibration step requires two fresh touchscreen taps;
- rapid double-taps are accepted as two distinct presses;
- Near/Far/Ramping yellow System states remain canonical on SRVR and CTRL-TS;
- `.06.04` automatic update path remains unchanged;
- W1P independent VEL watchdog remains 500 ms;
- SRVR non-zero VEL refresh remains approximately 150 ms;
- AI0 E-stop / AI1 joystick mapping remains unchanged;
- predictive/dynamic and hard limits remain unchanged;
- Leadshine velocity/Modbus architecture remains unchanged.
