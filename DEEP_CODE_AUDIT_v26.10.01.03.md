# HV P2P v26.10.01.03 deep code audit / closure

## v26.10.01.03 field-feedback addendum

Additional bench testing found that v26.10.01.02's automatic firmware-authority
recheck solved the reboot requirement but introduced a real-time regression: CTRL
performed a blocking HTTP manifest request every two seconds in the same main loop
that samples AI1 and transmits the 20 Hz joystick A7 packet. Network latency could
therefore freeze the displayed joystick value for roughly 1-2 seconds. W1P had the
same architectural issue in its drive loop.

v26.10.01.03 replaces healthy-loop HTTP polling with lightweight SRVR UDP release
beacons. A matched CTRL reads `srvr_fw` from the normal DSP1 packet; W1P receives
`SRVR_FW`. Matching versions return immediately with no HTTP. A changed release
clears the firmware match and enters the pre-existing fail-closed authority/OTA
path; W1P stops and inhibits Servo Enable before that path can block. Automatic
release convergence is therefore retained without putting network HTTP waits in a
real-time motion-input loop.

The same bench cycle exposed a Setup semantics issue: the joystick wizard had
placed its captured range in a draft until Apply, so the visible Percentage could
continue using the old range. In v26.10.01.03 the final Right capture immediately
commits/persists the complete Left/Centre/Right range. The Setup readout is based
on that calibrated mapping. Per operator request, Settings and Free-D now auto-save
each accepted edit and the footer Apply/Reset controls have been removed.

The v26.10.01.02 fixes remain retained: stale-release reporting is rejected, the
CTRL-TS boot JPEG is replaced by the dedicated update screen on FW_BEGIN, progress
redraw is throttled, and E-stop source formatting does not generate
`E-STOP | / W1P`.

## Scope and baseline

This revision was audited and modified directly from the attached authoritative
`HV P2P v26.09.29.06` source. The approved .06 UI/layout and existing motion and
safety architecture were retained unless a reported defect required a change.
GitHub Actions remains the authoritative native compiler; physical RS485, E-stop,
Leadshine and loaded-motion behaviour remain commissioning/bench gates.

## 1. CTRL AI0 / AI1 root cause and closure

The .06 mux constants themselves were correct: AI0 used the SGM58031 AI0-to-GND
configuration and AI1 used AI1-to-GND. The defect was transaction ownership.
`readJoystickAxis()` read the conversion register while assuming the converter
was already on AI1, and `sampleCtrlEstopAI0()` could return on an AI0 read failure
before restoring AI1. Health/diagnostic readers could also consume whichever mux
channel happened to be active and assign it a semantic label.

v26.10.01.03 makes channel selection part of each analogue transaction. The mux
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

v26.10.01.03 makes position-reference validity non-persistent authority. SRVR
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

v26.10.01.03 fixes polarity once at the CTRL input boundary: physical Left maps
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

v26.10.01.03 creates a dedicated runtime firmware-update screen when needed and
makes the updater the exclusive display owner from update start through verified
completion/reboot. It shows connection state, stable phase/percentage and a
progress bar. Normal CFG/HMI screen updates, link-state drawing and keepalive
rendering are ignored/suspended while update ownership is active; RS485/update
servicing remains active.

## Preserved control/safety contracts

- CTRL AI0 E-stop / AI1 joystick / common AGND intended wiring.
- 8-sample trimmed joystick acquisition and SRVR centre-drift management.
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
