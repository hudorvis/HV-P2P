# HV P2P v26.10.02.01 change summary

v26.10.02.01 is the first 2 October 2026 revision and is built directly from
v26.10.01.04. GitHub Actions remains the authoritative native compiler.

## 1. CTRL-TS OTA screen stability

The v26.10.01.04 video shows a real RGB scanout corruption frame while the
firmware dashboard itself remains selected. Two mechanisms were present:

- the .04 main loop could hold the LVGL mutex while an incoming `FW_BLOCK`
  executed `Update.write()`; and
- on ESP32-S3 RGB panels, flash programming and PSRAM/RGB DMA share memory/cache
  resources, so OTA flash activity can disturb the panel scanout even when no
  other LVGL screen is being drawn.

v26.10.02.01 addresses both boundaries. Firmware blocks are processed without
holding the LVGL mutex; the opaque firmware dashboard is fully rendered before
`Update.begin()`; RGB PCLK is temporarily reduced to 6 MHz for CTRL-TS flash
programming; the RGB stream is re-aligned after each flash block; failure restores
the normal 16 MHz PCLK; and the pinned Waveshare LVGL port is patched by GitHub
Actions from a 10-line to a 20-line RGB bounce buffer. Normal application screens
remain unable to overwrite the dashboard while firmware ownership is active.

This is a targeted mitigation for the observed hardware/driver interaction. A
successful source/static check cannot substitute for the physical 7-inch panel
bench test, so visual stability remains an explicit release gate.

## 2. One firmware dashboard for W1P / CTRL / CTRL-TS

CTRL-TS now has one firmware-update dashboard with three independent rows and
progress bars: **W1P**, **CTRL**, and **CTRL-TS**. Each row shows the current phase
and percentage.

- CTRL reports its authority-download progress directly over CTRL->CTRL-TS RS485,
  including while its normal Ethernet/control loop is occupied by OTA.
- W1P reports progress to SRVR; SRVR relays that state in the existing display
  packet to CTRL/CTRL-TS.
- CTRL-TS reports its own local receive/write/verify state directly.

The dashboard keeps exclusive screen ownership while any row is active and holds
briefly after completion so the operator can see the result. The first upgrade
*into* this revision cannot retroactively show the new CTRL row while the display
is still running older firmware; from v26.10.02.01 onward, subsequent matched
release updates have the unified dashboard available before the next CTRL/W1P
update begins.

## 3. Calibration wizard on CTRL-TS

v26.10.01.04 added `Joystick Calibration` to the AUX assignment vocabulary and
made the backend action state-aware, but CTRL-TS still had no visible calibration
wizard panel. That made an AUX confirmation appear to do nothing/reset even though
SRVR calibration state had changed.

v26.10.02.01 sends explicit calibration state (`kind`, `step`, title and
instruction) in the display packet and provides one touchscreen wizard overlay for
**Limit Calibration**, **Winch Calibration**, and **Joystick Calibration**. The
five AUX cards remain visible and touchable; the assigned AUX remains the step
Confirm control. When a step advances, the two-second `Confirmed` visual latch is
cleared immediately so the next step is ready to use.

There is no intentional `ESP.restart()` in any calibration action. CTRL-TS now
also prints `esp_reset_reason()` at boot, so if the hardware actually resets during
a future calibration bench test, the serial log will identify the ESP reset class
instead of relying on the visual symptom alone.

## Retained v26.10.01.04 / .03 behaviour

- runtime SRVR loss returns CTRL-TS to the original `Waiting for SRVR` splash;
- direct old-release OTA compatibility bridge and current non-blocking release
  authority remain;
- CTRL-TS E-Stop/source formatting and unsupported square-glyph fixes remain;
- 25 ms / five-sample low-latency joystick acquisition remains;
- Settings and Free-D remain auto-save pages with no Apply/Reset footer;
- joystick calibration immediately activates/saves the captured calibrated range;
- AI0 is CTRL E-stop and AI1 is joystick with verified mux ownership;
- W1P independent 500 ms velocity watchdog, SRVR ~150 ms non-zero VEL refresh,
  predictive stopping, hard limits, Servo Enable and emergency-stop protections
  remain unchanged.

## Regression/build status

The source regression suite now additionally locks the unified three-device
firmware dashboard, CTRL/W1P progress transport, calibration overlay, reset-reason
diagnostic, OTA-before-flash full render, 6 MHz update PCLK / RGB restart
mitigation, and 20-line Waveshare bounce-buffer build patch.

macOS short version is `26.10.2`, bundle build `2610.2.1`, full release
`26.10.02.01`. Native ESP32 and frozen desktop compilation is intentionally left
to GitHub Actions; physical RGB-panel, RS485, Leadshine and motion validation
remain bench gates.
