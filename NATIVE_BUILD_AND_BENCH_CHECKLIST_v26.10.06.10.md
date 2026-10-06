# HV P2P v26.10.06.10 native build and bench checklist

## GitHub CI

- [ ] Ubuntu source/static suite passes, including `HMI_DISPLAY_BOUND_TRANSPORT_0610_PASS`.
- [ ] macOS Intel `python -m tools.test_backend_logic` passes.
- [ ] macOS Apple Silicon `python -m tools.test_backend_logic` passes.
- [ ] Windows x64 `python -m tools.test_backend_logic` passes.
- [ ] Native CTRL-TS compile passes.
- [ ] Native CTRL compile passes with staged CTRL-TS image.
- [ ] Native W1P compile passes.
- [ ] Frozen desktop smoke tests pass on all platforms.

## Primary bench test

Start with the currently installed `.06.09` field firmware and launch the GitHub-built `.06.10` SRVR normally.

- [ ] Automatic update remains normal; no manual reboot is required.
- [ ] After convergence, CTRL-TS shows SRVR's actual `System | Uncalibrated`/current state rather than local `System | Active` fallback.
- [ ] AUX tiles immediately show the configured SRVR assignments rather than `Aux 1..5`.
- [ ] Position, To Near/To Far, Current Speed, mode and presets populate.
- [ ] Move the joystick: SRVR motion/control remains normal and CTRL-TS position/speed update live.
- [ ] Leave the system stationary for >3 seconds: the display remains populated through normal keepalive behavior.
- [ ] Close SRVR: CTRL-TS returns to the appropriate Waiting/E-stop presentation; restart SRVR and confirm live display data self-recovers without rebooting CTRL or CTRL-TS.

## Locked behavior regression

- [ ] W1P 500 ms independent VEL watchdog unchanged.
- [ ] Normal SRVR non-zero VEL cadence unchanged.
- [ ] Calibration/AUX two-step behavior unchanged.
- [ ] `System | Ramping`, Near Limit and Far Limit semantics unchanged.
- [ ] CTRL-TS verified-sample progress interpolation unchanged.
- [ ] Encoder/Leadshine RS485 path unchanged.

## Source verification completed

- 370 EdgeBox integration checks PASS.
- All historical source regressions PASS.
- `.06.10` bound-display transport regression PASS.
- 53 build-pipeline checks PASS.
- Release consistency, source hygiene, Python syntax and SRVR preflight PASS.

PySide6 is not installed in the source-audit environment, so exact desktop runtime testing remains a GitHub CI gate.
