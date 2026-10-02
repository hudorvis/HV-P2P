# HV P2P v26.10.02.02 deep code audit / closure

## v26.10.02.02 calibration-display field-video addendum

Four bench videos were reviewed frame-by-frame. IMG_4951 and IMG_4952 show the
main face stable through AUX `Confirm?`, then the travel/info region becomes
vertically repeated/duplicated before the panel goes dark and returns to the
normal boot splash. The splash subsequently shows the startup countdown form
`CTRL OK | SRVR OK | starting in ...`, which is generated only by
`show_boot_splash()` during `setup()`. IMG_4954 shows the wizard can also open
cleanly, making the defect intermittent rather than a deterministic calibration
state-machine restart.

Source tracing found that `apply_calibration_overlay_fields()` in .01 called
`lv_obj_move_foreground(g_cal_overlay)` for every active HMI packet and continued
to repaint all covered travel/Drive/Speed/Position widgets. The corrupted region
in the video is the same region owned by that overlay. .02 makes overlay
ownership edge-triggered and freezes covered rendering while active. No
calibration code path intentionally calls `ESP.restart()`; reset-reason logging
remains enabled for any recurrence.

## v26.10.02.02 field-feedback addendum

This revision was traced directly from v26.10.01.04 after the 2 October bench
video and calibration feedback.

1. **CTRL-TS update corruption:** the video contains a corrupted RGB frame even
   though the firmware dashboard remains the active LVGL screen. In .04 an OTA
   block could also execute `Update.write()` while the main loop held the LVGL
   mutex. v26.10.02.02 removes that lock overlap and treats the remaining issue as
   an ESP32-S3 RGB/flash/PSRAM scanout problem: the dashboard is rendered before
   `Update.begin()`, RGB PCLK is reduced to 6 MHz during local flash writes, the
   RGB panel is restarted/re-aligned after each block, and the GitHub-pinned
   Waveshare port is patched to a 20-line bounce buffer. A failed update restores
   the normal 16 MHz clock.
2. **No operator indication for CTRL/W1P OTA:** .04 exposed firmware state in SRVR
   but CTRL-TS only had useful local CTRL-TS progress. v26.10.02.02 adds one
   three-row dashboard. CTRL sends `FWSTAT` directly over RS485 from its authority
   download callback; W1P sends `FW_PROGRESS` to SRVR and SRVR relays it; CTRL-TS
   owns its local row. Any active row owns the display.
3. **Joystick Calibration AUX looked like a reboot:** .04 backend had the new AUX
   action and stateful open/advance logic, but the touchscreen had no joystick (or
   common calibration) wizard UI to render the state. v26.10.02.02 adds an
   explicit overlay for Limit, Winch and Joystick calibration while leaving AUX
   cards visible as the Confirm controls. Advancing a step clears the previous
   Confirmed latch immediately. No calibration code calls `ESP.restart()`; boot
   logging now records `esp_reset_reason()` so a genuine reset can be diagnosed
   if one is observed again.

The first migration into this revision has one unavoidable visibility limit: an
older CTRL-TS cannot display UI code it does not yet contain. Because CTRL carries
the staged CTRL-TS image, CTRL must first reach the new release before it can
install the new touchscreen firmware. Once v26.10.02.02 is installed, future
matched upgrades can show CTRL, W1P and CTRL-TS progress on the already-capable
touchscreen.

## Scope and baseline

The current revision is modified directly from v26.10.01.04, whose audited lineage
continues from the attached authoritative `HV P2P v26.09.29.06` baseline. Approved
UI/layout and existing motion/safety architecture remain unchanged except where a
reported defect requires correction.
GitHub Actions remains the authoritative native compiler; physical RS485, E-stop,
Leadshine and loaded-motion behaviour remain commissioning/bench gates.

## 1. CTRL AI0 / AI1 root cause and closure

The .06 mux constants themselves were correct: AI0 used the SGM58031 AI0-to-GND
configuration and AI1 used AI1-to-GND. The defect was transaction ownership.
`readJoystickAxis()` read the conversion register while assuming the converter
was already on AI1, and `sampleCtrlEstopAI0()` could return on an AI0 read failure
before restoring AI1. Health/diagnostic readers could also consume whichever mux
channel happened to be active and assign it a semantic label.

v26.10.02.02 makes channel selection part of each analogue transaction. The mux
write is read back/verified, enough conversion time is allowed, stale data is
discarded, and the requested channel is then sampled. AI0 E-stop sampling has a
guaranteed AI1 restore path. Diagnostic joystick voltage/raw values come from the
verified cached AI1 acquisition rather than an unqualified conversion-register
read.

A secondary .06 ambiguity was also removed: CTRL-TS link failure and firmware
authority failure were ORed into the same `FLAG_ESTOP_PRESSED` bit as the physical
AI0 E-stop. They remain fail-safe, but now use dedicated CTRL HMI/FW safety bits,
so SRVR does not incorrectly describe those sources as a physical CTRL E-stop.

## 2. Status priority and calibration/reference lifetime

In .06 `_not_calibrated` started true but was loaded/saved as configuration state,
allowing a previous position reference to survive a complete new session. The main
SRVR banner also considered only E-stop/safety for green readiness, while a
separate CTRL-TS packet path already knew about an uncalibrated yellow state.

v26.10.02.02 makes position-reference validity non-persistent authority. SRVR
starts uncalibrated regardless of saved `not_calibrated_mode`, and imported Run
configuration cannot clear that requirement. W1P now publishes a per-boot random
`BOOT_ID`; a new W1P session or changed boot ID invalidates an established runtime
reference. Existing Limit Calibration and Slip/re-reference paths still clear the
runtime uncalibrated state when the operator deliberately establishes a known
position.

One status resolver now enforces the intended priority: safety/fault/E-stop ->
red; otherwise uncalibrated -> yellow `System Un-Calibrated`; otherwise -> green
`System Ready`. Missing/unsafe W1P contributes a W1P safety source even in Virtual
position mode, so a disconnected W1P cannot be hidden by a display/simulation
choice. Multiple safety sources are combined, including `CTRL & W1P` when both
are unsafe.

## 3. Joystick direction root cause and closure

The installed APEM/AI1 voltage polarity was opposite the .06 raw-axis formula.
SRVR then defaulted `reverse_joystick=True` as a downstream compensation. That
compensation was not applied consistently to the Value/Percentage readouts and
could double-invert an explicitly captured Left/Centre/Right calibration.

v26.10.02.02 fixes polarity once at the CTRL input boundary: physical Left maps
to negative axis and physical Right to positive. SRVR defaults to Normal and the
calibrated readout, joystick request and limit-direction path share that sign.
The configuration migration preserves identity defaults and sign-migrates actual
legacy captures exactly once, including the older `joy_cal` storage form. The
operator's optional Direction setting remains available and is applied only once
after calibration.

## 4. CTRL-TS firmware-update display root cause and closure

The .06 firmware progress objects belonged to the boot splash. After normal
startup those LVGL objects were deleted/null, yet runtime `FW_BEGIN/FW_BLOCK`
handlers continued attempting to update them while the normal HMI/link timers
kept rendering. The updater therefore had no persistent post-boot screen owner.

v26.10.02.02 creates a dedicated runtime firmware-update screen when needed and
makes the updater the exclusive display owner from update start through verified
completion/reboot. It shows connection state, stable phase/percentage and a
progress bar. Normal CFG/HMI screen updates, link-state drawing and keepalive
rendering are ignored/suspended while update ownership is active; RS485/update
servicing remains active.

## Preserved control/safety contracts

- CTRL AI0 E-stop / AI1 joystick / common AGND intended wiring.
- 5-sample low-latency trimmed joystick acquisition and SRVR centre-drift management.
- W1P independent 500 ms velocity freshness watchdog.
- SRVR non-zero VEL refresh around 150 ms.
- predictive stopping and W1P local dynamic soft-limit protection.
- Near/Far hard-limit architecture and service/calibration protections.
- Preset Short Names / Long Names and SRVR Value / Percentage UI.
- CTRL <-> CTRL-TS hardened framed RS485 automatic updater.
- W1P <-> Leadshine Modbus RTU velocity-control and uphill/downhill Speed-mode
  regulation architecture.

## Validation boundary

The source/static regression suite is the local release gate. The repository
workflow remains responsible for native Arduino compilation, exact CTRL-TS image
staging into CTRL, and frozen Windows/macOS SRVR builds. No locally fabricated
ESP32 application binaries are included as a substitute for those GitHub Actions
outputs.
