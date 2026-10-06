# HV P2P v26.10.06.05 native-build and bench checklist

## GitHub gate

1. Upload the complete `.06.05` source to the repository.
2. Confirm CTRL-TS, CTRL and W1P native compilation succeeds.
3. Confirm macOS Intel, macOS Apple Silicon and Windows SRVR source/runtime/frozen tests pass.
4. Confirm the matched release artifact contains `.06.05` SRVR and firmware outputs.

## Calibration confirmation bench test

Test all three touchscreen calibration assignments: Joystick, Limit and Winch.

For every wizard step:

1. Confirm the assigned AUX tile begins in Ready state.
2. First tap must select the tile and display `Confirm?`; it must not execute the step.
3. Second tap must execute the action and display the confirmed state.
4. After the wizard advances, the next step must return to Ready and again require two fresh taps.
5. Repeat with a deliberately fast double-tap. Two distinct taps should work without waiting 250 ms.
6. A third accidental tap while the old step is still Confirmed must not double-advance the wizard.

## New System status bench test

With normal calibrated operation and no service/fault state:

1. More than 1 m from each endpoint and outside the active ramp zone: `System | Active` green.
2. Move toward an endpoint inside its configured ramp zone but remain more than 1 m from the endpoint: `System | Ramping` yellow.
3. Enter 1.0 m of Near: `System | Near Limit` yellow.
4. Enter 1.0 m of Far: `System | Far Limit` yellow.
5. Confirm SRVR and CTRL-TS show the same status simultaneously.
6. Trigger a genuine E-stop/fault while in any of the above zones: red E-stop/fault must take priority immediately.
7. Confirm calibration, Battery Change and Uncalibrated wording still takes priority over the new normal-motion labels.

## Locked regression checks

- `.06.04` automatic update path still completes without manual reboot.
- W1P independent VEL watchdog remains 500 ms.
- SRVR non-zero VEL refresh remains approximately 150 ms.
- AI0 E-stop / AI1 joystick mapping unchanged.
- Predictive/dynamic and hard limits unchanged.
- Leadshine velocity/Modbus architecture unchanged.
