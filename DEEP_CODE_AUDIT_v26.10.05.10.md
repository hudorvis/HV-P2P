# HV P2P v26.10.05.10 targeted code audit

Date: 2026-10-05

Starting point: `HV P2P v26.10.05.09`, preserving the `.05.09` fixes derived from authoritative `.05.06`.

## Finding A — Limit Calibration displayed the wrong coordinate after Near

`backend.py::_build_controller_display_packet()` populated `cal_pos` from `state.pos_m`. Because `.05.09` intentionally keeps the previous valid calibration live until the final Reference commit, `state.pos_m` remains in the old coordinate system during the staged wizard. This produced the contradictory display `NEAR 0.00 m` with a Current Winch Position such as `9.51 m`.

The fix adds `_limit_calibration_display_position()`. Before Near capture it reports the live coordinate. After Near capture it reports absolute travel from the staged Near point, preferring raw encoder delta on hardware. This is used by CTRL-TS `cal_pos`, SRVR `limitCalibrationCaptures.current`, and the SRVR calibration SpanDiagram. It does not call `SYNC_POS`, change limits, or alter the transactional commit boundary.

## Finding B — Shortcuts/System overflow was deterministic QML geometry

The Shortcuts panel inner height is 232 scaled pixels. After the 27 px heading, 27 px tab row and outer spacing, about 172 px remain. The System column requested five 32 px rows plus four 5 px gaps = 180 px, so the last controls necessarily protruded below the panel.

The fix changes the System rows to 31 px—the same height used by Limits Save/Recall/Slip—and inter-row spacing to 2 px, for 163 px total. No component styling changes are required.

## Finding C — `Practice Mode` was truncated before reaching CTRL-TS

`_aux_action_label()` correctly produced `Drive Mode | Practice Mode`. The following `_display_field()` call used its default 24-character limit. Because the complete label is 26 characters, the source packet was truncated to `Drive Mode / Practice Mo` before CTRL forwarding or LVGL rendering.

The fix explicitly allows 40 characters for AUX fields. The packet remains safely below the 3072-byte RS485 payload limit and the touchscreen label already has enough horizontal space at Montserrat 10.

## Secondary checks

- CTRL and W1P control/safety paths were not changed.
- CTRL-TS tile dimensions/font size were not reduced.
- Limit Calibration remains transactional and Cancel remains non-destructive.
- W1P STATUS arbitration, SRVR background liveness and VEL bridging from `.05.09` remain unchanged.
- New static and PySide runtime regression coverage checks the Near-relative coordinate, System panel geometry and full AUX label transport.
