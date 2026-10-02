# HV P2P v26.10.02.03 change summary

v26.10.02.03 is the recovery/safety successor to v26.10.02.02. It keeps the
calibration-wizard fixes from .02 while deliberately removing the low-level RGB
OTA experiment introduced in v26.10.02.01 and inherited by .02. GitHub Actions
remains the authoritative native compiler.

## Why this revision exists

Bench testing of .01/.02 showed the Waveshare CTRL-TS could enter corrupted RGB
scanout states (green/blue/black/white flashing, displaced/duplicated rows and
incorrect-looking scale) while/after self-update. A full reboot could restore the
normal application, which pointed to display/scanout state rather than permanent
panel damage.

The source audit identified three release changes that should not have been made
on an actively scanned RGB panel during self-flash:

- the pinned Waveshare RGB bounce buffer was changed from its upstream 10-line
  value to 20 lines;
- RGB pixel clock was changed at runtime during OTA;
- the RGB panel DMA/stream was restarted after individual `Update.write()` calls.

All three are removed in .03. The GitHub build now leaves the pinned Waveshare
RGB buffer/display configuration at its upstream value and applies only the
existing narrow CH422G address-symbol compatibility patch required by the pinned
IO-expander library.

## Safe two-stage CTRL-TS self-update

CTRL-TS no longer writes its own flash while RGB/LVGL is running.

1. The normal UI receives a valid `FW_BEGIN`, verifies the exact target hardware,
   protocol, version and SHA metadata, and stages that exact target in a tiny
   **internal-DRAM `__NOINIT_ATTR` handoff**. This is RAM-only: the live display
   stage performs no `Preferences`/NVS or OTA flash write.
2. It shows **Restarting in safe update mode**, asks CTRL to retry after reboot,
   turns the LCD backlight off, asserts LCD reset through the CH422G expander and
   deliberately calls `ESP.restart()`.
3. On the next boot, the handoff is accepted only for `ESP_RST_SW` and only after
   magic, strict version/SHA format and checksum validation. CTRL-TS then starts
   only UART/RS485 and the CH422G blackout path. It does **not** start PSRAM RGB
   framebuffers, the RGB bus, touch or LVGL.
4. CTRL re-establishes HELLO, sees the old image identity, and retries the exact
   staged image. Only this headless boot can reach `Update.begin()`/`Update.write()`.
5. Size and SHA-256 are verified and firmware identity metadata is committed for
   the new OTA partition while the display is still headless, then CTRL-TS reboots
   normally. The no-init handoff is consumed on entry, so an unexpected headless
   reset falls back to the known-good application instead of boot-looping.

If no firmware transfer starts while safe-update mode is waiting, a 60-second
recovery guard returns to the normal UI rather than leaving the screen black.
A power/brownout/watchdog reset does not consume a stale handoff; only the deliberate
software restart requested by a validated `FW_BEGIN` may enter headless mode.

This intentionally means the CTRL-TS panel goes dark during **its own** flash
programming phase. W1P and CTRL update progress can still be shown live on the
firmware dashboard while the touchscreen application is running. Reliability of
the self-flash path takes priority over drawing a live percentage from the same
MCU while it rewrites its flash.

## Automatic release convergence

CTRL now accepts both the existing `DSP1|...|srvr_fw=` release advertisement and
a dedicated lightweight `SRVR_FW|version=...` UDP beacon. SRVR sends the dedicated
CTRL beacon every 500 ms without putting HTTP work in CTRL's 25 ms control loop.
The asynchronous legacy `/update/app` bridge remains for older field firmware and
now treats either fresh CTRL control telemetry **or** fresh CTRL authority/HMI
status as proof the old node is present. A version mismatch remains fail-closed
before any upload begins.

CTRL also recognises `fw_safe_reboot_retry` as the expected first stage of the new
CTRL-TS update, immediately returns to HELLO discovery, and resumes the transfer
when the headless updater appears.

### One-time migration gate from pre-.03 CTRL-TS firmware

A critical secondary audit finding is that the **first** update into .03 cannot be
made safe by .03 code if the receiver is still running .02.01/.02.02: the old
receiver would be the code performing the flash. Therefore .03 introduces an
explicit capability boundary:

- .03 CTRL-TS HELLO identity advertises `safe_ota=1`;
- CTRL records that capability and refuses to send automatic CTRL-TS firmware to
  any mismatched receiver that does not advertise it;
- SRVR reports **Manual USB bootstrap required** for this state;
- after a one-time manual .03 bootstrap, all future automatic CTRL-TS updates use
  the headless path;
- .03 CTRL-TS rejects numerically older FW_BEGIN versions, preventing an older
  CTRL carrier from downgrading a manually recovered touchscreen.

This intentionally trades one manual recovery flash for a provable boundary: the
known-bad pre-.03 self-updater is never invoked by .03.

## Calibration/display fixes retained and strengthened

The .02 calibration-overlay correction is retained:

- no calibration `lv_obj_move_foreground()` calls at packet rate;
- the opaque wizard is shown/hidden only on state transitions;
- covered Travel/Drive/Speed/Position widgets are not repainted underneath it;
- redundant explicit label invalidation remains removed;
- AUX Confirm state is now cleared on **kind/step identity** changes, not only
  title changes, so Joystick Left/Centre/Right can advance even though the title
  remains `Joystick Calibration`.

Joystick step 1 remains exactly:

**Hold Joystick Left, then press Confirm**

The lower `Use the assigned AUX...` description row remains removed.

## Motion/safety architecture preserved

No intended change was made to the established winch motion architecture: CTRL
AI0 remains E-stop and AI1 joystick; W1P retains the independent 500 ms velocity
freshness watchdog; SRVR retains ~150 ms non-zero VEL refresh; predictive
stopping/dynamic limits, hard limits, E-stop gates, Servo Enable/brake protections
and Leadshine control architecture remain in place.

## Validation

The local source suite now contains a dedicated `test_ctrl_ts_safe_update_contract.py`
that fails if RGB PCLK/restart manipulation or the 20-line bounce-buffer patch is
reintroduced, and verifies that flash writes are gated behind the headless boot.
The integration validator contains 357 source checks in this revision; build
pipeline validation contains 53 checks. Native ESP32 and frozen desktop builds
remain GitHub Actions gates, and physical CTRL-TS/RS485 behaviour remains a bench
acceptance gate.

macOS short version: `26.10.2`  
macOS bundle build: `2610.2.3`  
Full release: `v26.10.02.03`
