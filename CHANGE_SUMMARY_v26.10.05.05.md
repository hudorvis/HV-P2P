# HV P2P v26.10.05.05 change summary

Date: 2026-10-05

Authoritative lineage: `HV P2P v26.10.05.04 - GitHub Ready Source.zip` -> this CI/runtime contract hotfix.

## GitHub runtime failure addressed

The `.05.04` production backend intentionally changed operator-facing Current Speed to display a positive magnitude, but the change was applied too early in `_build_controller_display_packet()`. That made DSP1/HMM1 transport speed unsigned as well, while `tools/test_backend_logic.py` correctly continued to require signed transport values (`-1.25 m/s`, `-4.50 km/h`) for reverse direction.

## Correction

- DSP1/HMM1 now retain the signed `current_speed_mps` value on the wire. Direction therefore remains available for transport diagnostics and any downstream direction-aware interpretation.
- SRVR's public `currentSpeed` property continues to use `abs(...)`, so operator Current Speed remains positive.
- CTRL-TS continues to render both m/s and km/h with `fabsf(...)`, so reverse motion still displays as a positive magnitude.
- `test_bench_regression_0504.py` now enforces this layering explicitly: signed transport + magnitude-only operator presentation.

## Preserved behavior

No W1P motion/safety logic, CTRL/CTRL-TS RS485 scheduling, updater coordination, calibration flow, QML layout or Leadshine architecture is changed by this hotfix.

## Verification

The complete source/preflight suite must pass from the final `.05.05` layout. GitHub Actions remains authoritative for the PySide6 runtime test and native ESP32/desktop compilation.
