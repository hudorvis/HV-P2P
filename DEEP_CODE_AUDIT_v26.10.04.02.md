# HV P2P v26.10.04.02 — CTRL-TS progress, AUX text and ramp-display audit

Date: 2026-10-04

Authoritative base: `HV P2P v26.10.04.01 - GitHub Ready Source.zip`.

## Bench evidence reviewed

- `.04.01` resolved the common CTRL-TS AUX-confirm reboot; Drive Mode, Battery Change Mode and Joystick Calibration can now be operated from CTRL-TS without the prior post-confirm reset.
- SRVR shutdown now causes the intended immediate CTRL-TS splash/waiting transition.
- CTRL-TS firmware progress can briefly appear and then go black during the update sequence.
- Drive Mode AUX value `Practice Mode` is clipped to `Practice Mo` despite unused horizontal tile space.
- CTRL-TS Near/Far ramp zones do not match the wedge-like ramp regions shown by SRVR.

## 1. CTRL firmware percentage suppression

CTRL intentionally marks ordinary HMI compatibility false when its SRVR-authority OTA begins. The CTRL progress callback nevertheless called the ordinary HMI text sender, whose normal-traffic gate requires HMI compatibility. The result is a self-contradictory path: the code generating real CTRL update percentages can be prevented from putting those percentages on RS485 precisely while CTRL is updating.

`.04.02` adds `hmiSendFirmwareStatusText()`. It bypasses only the compatibility condition needed for OTA progress and preserves the transport arbiter: it refuses to transmit while CTRL-TS firmware transfer owns the bus, while a POLL/EVENT transaction is outstanding, or during post-timeout bus recovery. Successful sends also restart the normal POLL interval so the touchscreen gets a quiet apply/render window.

## 2. Coordinated three-device progress order

CTRL-TS already has W1P, CTRL and CTRL-TS rows, but entering the CTRL-TS safe updater makes the screen unavailable by design. `.04.02` therefore keeps CTRL-TS in normal runtime while either SRVR `fw_ctrl_active` or `fw_w1p_active` is true. The repeated HELLO/update decision retries automatically, so CTRL-TS becomes the last ESP32 to self-program.

CTRL and W1P phase/percentage are also carried in compact `HMS1`, and CTRL-TS applies those firmware fields even while the firmware dashboard owns the display. This removes dependency on the ~4 Hz bulk HMI packet for update-row progress.

Before the final self-update handoff, CTRL-TS displays `Preparing safe updater` for about 900 ms. It then deliberately reboots into the existing display-off/headless updater. `Update.begin()`/`Update.write()` remain confined to that headless boot before normal LCD/LVGL initialization. Consequently, exact CTRL-TS self-flash percentage continues on SRVR while the physical touchscreen is black. Keeping live LVGL/RGB rendering during its own flash would undo the safety architecture that was introduced specifically to avoid flash/external-memory/display contention.

## 3. Practice Mode clipping

The AUX action label remains unchanged. The AUX value label was previously inset 8 px on both sides and used Montserrat 12. `Practice Mode` could wrap the final characters below the visible tile height. `.04.02` changes only that value label to x=4, width `AUX_W-8`, Montserrat 10 and `LV_LABEL_LONG_CLIP`, leaving the approved tile dimensions intact.

## 4. Near/Far ramp geometry

SRVR's `SpanDiagram` depicts each ramp zone as a wedge from the hard limit to the configured ramp boundary. CTRL-TS previously represented the same numerical settings with a thin rectangular band, which was not visually equivalent.

CTRL-TS now calculates the same normalized widths from the usable span and renders ten one-pixel rows per side. Row width increases linearly toward the ramp boundary, producing a low-memory wedge without allocating a canvas/framebuffer. `near`, `far`, `ramp_near` and `ramp_far` are in compact `HMS1`, so the geometry updates promptly after an SRVR Settings edit.

## Timing and safety review

No normal HMI timing was made more aggressive. The selected 60 ms POLL cadence, 250 ms response timeout, 300 ms late-response quiet period and 250 ms/4 Hz bulk display ceiling remain unchanged. Firmware progress is priority state but never pre-empts an outstanding half-duplex transaction. Firmware transfer itself remains exclusive.

W1P's 500 ms VEL freshness watchdog, ~150 ms SRVR non-zero VEL refresh, software Servo-Enable interlock, physical E-stop handling, hard limits, predictive stopping/dynamic soft limits and Leadshine velocity architecture are unchanged.

## Verification boundary

The source/regression/preflight suite verifies the progress transport gate, update ordering, safe headless boundary, AUX label geometry and ramp-wedge contract. Native ESP32 compilation and the physical three-node firmware update remain GitHub Actions/bench gates.
