# HV P2P v26.10.06.11 native build and bench checklist

## GitHub CI

- [ ] Ubuntu complete source/static suite passes, including `CTRL_TS_MARKER_SMOOTHNESS_0611_PASS`.
- [ ] macOS Intel `python -m tools.test_backend_logic` passes.
- [ ] macOS Apple Silicon `python -m tools.test_backend_logic` passes.
- [ ] Windows x64 `python -m tools.test_backend_logic` passes.
- [ ] Native CTRL-TS compile passes.
- [ ] Native CTRL compile passes with the staged CTRL-TS image.
- [ ] Native W1P compile passes.
- [ ] Frozen desktop smoke tests pass on all platforms.

## Primary cable-progress bench test

- [ ] Automatic update from the approved `v26.10.06.10` baseline converges normally with no manual node reboot.
- [ ] With Position Source = Virtual, move continuously across the span: SRVR Side/Top View and CTRL-TS marker both remain responsive; CTRL-TS should render smoothly at roughly its 50 Hz local loop rate.
- [ ] Reverse direction cleanly: the CTRL-TS marker must not overshoot the newest verified target or jump backwards as a correction to forward prediction.
- [ ] Stop abruptly: marker may complete movement only to the last received verified sample and then hold; it must not coast beyond it.
- [ ] With hardware Encoder/Leadshine source, repeat continuous motion: position samples remain source-limited by the unchanged 100 ms feedback poll, but visual interpolation should be fluid and free of duplicate HMI1/HMM1 segment restarts.
- [ ] Check Current Position / To Near / To Far / Speed readouts: their approved HMM1/bulk behavior remains unchanged.
- [ ] Exercise AUX1..AUX5 repeatedly during motion: touch response/confirmation remains reliable and no event is lost or duplicated.
- [ ] Enter/exit Joystick, Limit and Winch calibration: overlays and calibration semantics remain unchanged; marker resumes correctly after the overlay closes.
- [ ] Trigger normal status/ramp/limit states and confirm their timing/appearance is unchanged.
- [ ] Run an automatic CTRL-TS update: firmware transfer still exclusively owns the RS485 bus and completes normally.
- [ ] Disconnect/reconnect SRVR and CTRL-TS: normal waiting/status behavior remains unchanged and marker state self-recovers after compatibility/display traffic resumes.

## Locked behavior regression

- [ ] W1P `MODBUS_POLL_MS = 100` and 500 ms independent VEL watchdog unchanged.
- [ ] W1P STATUS 50 ms cadence unchanged.
- [ ] SRVR full DSP1 100 ms cadence unchanged.
- [ ] CTRL HMM1 80 ms gate and HMI1 250 ms gate unchanged.
- [ ] CTRL POLL interval 60 ms and reliable EVENT/ACK semantics unchanged.
- [ ] Motion control, predictive/hard limits, E-stop, calibration, AUX semantics and firmware authority unchanged.
