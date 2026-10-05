# HV P2P v26.10.05.05 deep code audit

Date: 2026-10-05

## Scope

Focused audit of the GitHub PySide runtime failure in `tools.test_backend_logic` after `.05.04` changed Current Speed presentation.

## Finding

The user requirement was presentation-specific: Current Speed should never show a negative number. SRVR already exposes `currentSpeed` using `abs(float(self.current_speed_mps))`, and CTRL-TS already formats its speed labels with `fabsf(...)`.

`.05.04` additionally changed `_build_controller_display_packet()` to apply `abs()` before serializing `speed_mps`/`speed_kmh`. That removed direction from DSP1/HMM1 and violated the existing backend runtime contract, which deliberately checks that reverse motion remains signed on the wire.

## Correction

`_build_controller_display_packet()` again serializes `float(self.current_speed_mps or 0.0)` directly. The wire remains signed; only operator presentation is absolute. CTRL simply relays those fields in HMM1, and CTRL-TS applies `fabsf()` only when drawing the labels.

This is the clean separation of concerns:

- control/internal velocity: signed;
- DSP1/HMM1 transport: signed;
- SRVR Current Speed UI: magnitude;
- CTRL-TS Current Speed UI: magnitude.

## Safety review

No motor command, soft-limit, predictive-stop, watchdog, E-stop, calibration, firmware-update or RS485 scheduling path is changed.
