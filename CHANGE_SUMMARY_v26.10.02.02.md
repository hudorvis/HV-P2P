# HV P2P v26.10.02.02 change summary

v26.10.02.02 is built directly from v26.10.02.01 after bench videos
`IMG_4951.mp4` through `IMG_4954.mp4` exposed an intermittent CTRL-TS
calibration-display failure. GitHub Actions remains the authoritative native
compiler.

## CTRL-TS calibration-screen reliability

The videos confirm two distinct outcomes from the same Joystick Calibration AUX
action. In IMG_4954 the wizard opens normally. In IMG_4951/IMG_4952 the travel
and Drive/Speed/Position region first turns into repeated/vertically duplicated
rows, then the display returns to the normal CTRL-TS boot splash and startup
countdown. This proves the event is a real controller restart rather than merely
the runtime `Waiting for SRVR` splash.

The v26.10.02.01 render path had a concrete high-load defect: every HMI packet
while `cal_active=1` unconditionally cleared the overlay HIDDEN flag and called
`lv_obj_move_foreground(g_cal_overlay)`, while the covered travel and
Drive/Speed/Position widgets continued receiving normal 20-40 Hz redraws
underneath the opaque overlay. The large calibration region was therefore being
reordered/invalidated repeatedly at the same time as hidden child widgets were
updating. This matches the corrupted screen region visible immediately before
the resets.

v26.10.02.02 changes calibration display ownership as follows:

- the calibration overlay is created last and permanently remains the top child;
- it is shown only on the inactive -> active transition and hidden only on the
  active -> inactive transition;
- there is no runtime `lv_obj_move_foreground()` for calibration;
- while the opaque wizard is visible, the underlying travel, preset markers,
  progress marker and Drive/Speed/Position labels are not repainted;
- model values continue to be parsed/cached, so the first packet after the wizard
  closes redraws the normal face from current values;
- `set_label_text_if_changed()` no longer explicitly invalidates a label after
  `lv_label_set_text()`, because LVGL already invalidates that object. This
  removes a second redundant redraw request on every changed label.

The existing serial `esp_reset_reason()` diagnostic remains. If a physical reset
occurs again after this change, the reset-class log is still the authoritative
way to distinguish watchdog, brownout and software reset causes.

## Joystick Calibration wording

Joystick step 1 now displays exactly:

**Hold Joystick Left, then press Confirm**

The previous lower description `Use the assigned AUX: press once for Confirm?,
then press again to confirm this step.` has been removed entirely. Centre and
Right steps use the same concise operator style.

## Retained behaviour

This revision does not change the motion/safety architecture introduced in prior
releases: AI0 remains CTRL E-stop, AI1 remains joystick, W1P retains the 500 ms
velocity freshness watchdog, SRVR keeps the ~150 ms non-zero VEL refresh,
predictive stopping/dynamic soft limits remain, firmware authority/update logic
remains, and all hard-limit/E-stop/Servo Enable protections remain unchanged.

## Validation

The source suite includes regression guards for one-time calibration overlay
ownership, no calibration `lv_obj_move_foreground()`, suppression of covered
background redraws, exact Joystick step wording and removal of the lower hint
row. Native ESP32 and frozen desktop builds remain GitHub Actions gates and the
physical 7-inch CTRL-TS remains the final display-stability acceptance test.

macOS short version remains `26.10.2`; bundle build is `2610.2.2`; full release
is `v26.10.02.02`.
