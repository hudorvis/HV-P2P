# HV P2P v26.10.06.09 native build and bench checklist

## GitHub CI

- [ ] Ubuntu source/static suite passes, including `ESTOP_BANNER_FIXTURE_CONTRACT_0609_PASS`.
- [ ] macOS Intel `python -m tools.test_backend_logic` passes.
- [ ] macOS Apple Silicon `python -m tools.test_backend_logic` passes.
- [ ] Windows x64 `python -m tools.test_backend_logic` passes the former line-752 E-stop banner assertion.
- [ ] Native CTRL-TS compile passes.
- [ ] Native CTRL compile passes with staged CTRL-TS image.
- [ ] Native W1P compile passes.
- [ ] Frozen desktop smoke tests pass on all platforms.

## Locked production regression

No new bench behavior is introduced by `.06.09`. Reconfirm only that `.06.08` behavior remains unchanged:

- [ ] Automatic CTRL -> W1P -> CTRL-TS update/recovery remains normal.
- [ ] CTRL-TS progress marker remains smooth sample-to-sample interpolation.
- [ ] `System | Ramping` remains yellow while stopped inside an end ramp zone.
- [ ] Calibration/AUX two-step confirmation remains deterministic.
- [ ] W1P Encoder/Leadshine path and independent 500 ms VEL watchdog remain unchanged.

## Source-only verification completed

- 370 EdgeBox integration checks PASS.
- All historical source regressions PASS.
- `.06.09` E-stop fixture contract PASS.
- 53 build-pipeline checks PASS.
- Release consistency, source hygiene, Python syntax and SRVR preflight PASS.

PySide6 is not installed in the source-audit environment, so the exact desktop runtime test remains a GitHub CI gate.
