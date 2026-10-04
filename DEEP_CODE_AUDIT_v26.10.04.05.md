# HV P2P v26.10.04.05 — updater, calibration, geometry and AUX-authority audit

Date: 2026-10-04

Authoritative base: `HV P2P v26.10.04.04 - GitHub Ready Source.zip`.

## 1. CTRL-TS black during its own update

The black phase is not a normal display failure. The safe CTRL-TS self-updater intentionally boots without RGB/LVGL/touch/PSRAM display workload while it writes the application partition. Earlier live-display/self-flash experiments were associated with corruption/reset instability, so `.04.05` does not reintroduce that architecture.

The operator handoff is improved instead:

1. CTRL/W1P update progress can remain visible on CTRL-TS while those external nodes update.
2. Immediately before CTRL-TS self-update, CTRL-TS displays `Preparing safe updater - SRVR shows self-flash progress` for about 1800 ms.
3. CTRL holds HMI rediscovery for about 3000 ms across the deliberate safe reboot.
4. The panel is then intentionally black only for the headless self-flash; SRVR remains the authoritative exact progress display.

A physical on-panel 0–100% display during the actual self-flash would require a resident updater capable of owning the display independently of the application being replaced.

## 2. Automatic update did not start until CTRL/CTRL-TS reboot

SRVR's legacy firmware convergence path was too dependent on the normal periodic service/session timing. A running old CTRL could report itself yet fail to trigger the push promptly until its session changed after reboot.

Correction: `_handle_ctrl_hmi_status()` can now schedule the legacy firmware push immediately from a fresh CTRL `HMI_STATUS`. `_try_start_legacy_firmware_push()` provides a thread-safe role reservation and retry guard, and the existing periodic service reuses the same helper rather than having a second ownership model.

No blocking firmware HTTP work is moved onto the high-rate receiver/UI thread; the helper only schedules/reserves the background update operation.

## 3. `System | Uncalibrated`

The former operator string `System Un-Calibrated` was hard-coded in both banner and display-state generation. Both now use the canonical `System | Uncalibrated`. Static regressions require that exact spelling/separator.

## 4. Joystick centre displayed ±0.1–0.3%

A small calibrated residual around centre is normal even after a good calibration. The motion system already applies its neutral/deadband rules, but the Settings readout exposed the raw calibrated residual, which made a safely neutral stick appear off-centre.

Correction: operator-facing joystick Value/Percentage properties pass through `_operator_joystick_axis()`. Values inside the configured neutral/deadband window display as exactly zero. Raw calibration, ADC samples and motion calculations are not modified.

## 5. Limit Calibration lacked Near / Ref / Far feedback

The wizard stored the values internally but did not expose a live capture map comparable to the Joystick Calibration readouts.

Correction:

- backend maintains `_limit_cal_pending = {near, ref, far}`;
- `limitCalibrationCaptures` exposes Near/Ref/Far plus Current Position;
- the SRVR popup renders all four values;
- DSP/calibration state carries `cal_pos`, `cal_near`, `cal_ref`, `cal_far`;
- CTRL includes those fields in the fast state packet only while calibration is active;
- CTRL-TS renders the values in the Limit Calibration overlay.

The property notifies on live `stateChanged`, not merely step transitions, so Current Position visibly changes during Virtual movement.

## 6. Virtual Limit Calibration appeared frozen

The Virtual integrator could move, but the Limit wizard did not show its live position, so the user only saw the final computed span after completion. `.04.05` initializes a Virtual position when the wizard begins if necessary and displays the live value throughout. Runtime tests advance the simulator during the wizard and verify Near/Far/Ref captures.

Virtual remains physically inhibited: no non-zero W1P VEL is emitted and any connected W1P is held at `STOP` + `SW_SRVON 0`.

## 7. CTRL-TS ramp / Ref / presets missing

Geometry had been split across state and bulk display paths, and CTRL-TS redraw triggers were not guaranteed when a geometry-only change occurred or when an overlay closed.

Correction: new `HMG1` is a compact change-driven geometry packet. CTRL caches the latest packet and sends it through the same half-duplex single-flight gate before bulk HMI telemetry. It carries Near/Far/Ref, normalized ramp fractions and preset geometry/visibility. CTRL-TS explicitly applies and redraws those elements when `HMG1` arrives and after calibration overlays close.

To protect RS485 margin, live position is not continuously placed into the priority path. Normal position remains in the 4 Hz bulk display packet; only active calibration gets faster current-position state.

## 8. CTRL-TS AUX labels did not match SRVR

The exact stale labels came from persisted `UIL1` presentation data on CTRL. `UIL1` originally included AUX text, so reconnect could overwrite live SRVR assignments after the correct state had already arrived.

Correction: `UIL1` no longer owns AUX semantics. CTRL defaults it to generic AUX placeholders; CTRL-TS ignores AUX assignment fields from layout; live SRVR AUX state is authoritative. CTRL also re-marks the latest state/geometry pending across reconnect/layout delivery so old NVS presentation data cannot win the race.

## 9. RS485 timing/safety review

The `.03.05+` transport invariants remain unchanged:

- one CTRL↔CTRL-TS half-duplex transaction at a time;
- no second POLL while a response is outstanding;
- no normal TEXT/HMI send while awaiting EVENT;
- explicit response timeout and late-response quiet window;
- EVENT/priority state ahead of bulk telemetry;
- bulk display capped at 4 Hz;
- firmware transfer owns the bus exclusively while active.

`HMG1` is change-driven and does not increase continuous bus load. Calibration-only live fields are gated to active wizard periods.

## 10. Safety boundary

No change was made to the W1P 500 ms velocity freshness watchdog, SRVR ~150 ms non-zero VEL refresh, AI0 E-stop / AI1 joystick mapping, physical hard limits, predictive stopping/dynamic soft limits or Leadshine velocity architecture.

## Verification boundary

Source/static regressions cover the new updater scheduling, handoff timings, status text, neutral display, Limit wizard, Virtual capture, AUX authority and HMG1 geometry behavior. Native firmware compilation and frozen PySide application builds remain GitHub Actions gates; physical system behavior remains bench acceptance.

## CTRL-TS system-state wording

The normal green state now renders as `System | Active`. The uncalibrated state passes through as `System | Uncalibrated`; service/calibration states retain the explicit `STATE | ...` prefix.
