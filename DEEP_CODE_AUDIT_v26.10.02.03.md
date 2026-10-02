# HV P2P v26.10.02.03 deep code audit / closure

## Scope

This audit was performed on the v26.10.02.03 working tree derived from
v26.10.02.02, with direct comparison back to v26.10.02.01 and the pre-RGB-change
v26.10.01.04 code. The purpose is to recover CTRL-TS reliability without losing
the calibration, status, joystick and firmware-authority fixes already made.

GitHub Actions/native compilation remains authoritative. The local audit can
prove source invariants and regression contracts, but cannot prove physical
Waveshare RGB stability or machine motion without the native build and bench.

## 1. Root cause/risk audit of the .01/.02 CTRL-TS regression

The .01 update-screen work introduced three low-level changes in the Waveshare
RGB path:

1. the pinned library's `LVGL_PORT_RGB_BOUNCE_BUFFER_SIZE` was patched from
   `LVGL_PORT_DISP_WIDTH * 10` to `* 20`;
2. RGB pixel clock was changed dynamically during OTA;
3. `esp_lcd_rgb_panel_restart()` was called around/after self-flash blocks.

Those changes remained in .02. Bench symptoms included colour cycling,
vertically displaced/duplicated image regions, scale-like corruption and recovery
after a complete reboot. They are therefore treated as unsafe release changes.

v26.10.02.03 removes all of them:

- no `esp_lcd_panel_rgb.h` dependency in CTRL-TS application code;
- no `esp_lcd_rgb_panel_set_pclk()`;
- no `esp_lcd_rgb_panel_restart()`;
- no firmware-specific RGB PCLK constants;
- `prepare_waveshare_library.py` no longer edits the RGB bounce-buffer macro;
- GitHub CI no longer asserts/creates a 20-line bounce buffer.

The pinned Waveshare library configuration is left at its upstream 10-line bounce
buffer/direct-mode/double-buffer configuration. The build helper only performs
the previously required CH422G address-symbol compatibility patch.

## 2. CTRL-TS self-update is now display-off/headless

The source now enforces a hard boundary: the running RGB/LVGL application can
validate and stage an update request, but it cannot call `Update.begin()` or
`Update.write()`.

### Normal displayed stage

`fw_handle_begin()` validates:

- hardware ID equals `WS-ESP32S3-7`;
- protocol equals the expected framed-RS485 protocol;
- image size is inside the conservative OTA slot;
- version follows the release format and is not a downgrade;
- SHA-256 metadata is exactly 64 hexadecimal characters;
- a finalized image cannot be overwritten by a late duplicate FW_BEGIN.

If the display runtime is active, it **does not write NVS or OTA flash**. Instead
it stages the exact requested version/SHA in an internal-DRAM `__NOINIT_ATTR`
structure using an invalidate-copy-checksum-publish sequence. It updates the
firmware dashboard to `Restarting in safe update mode`, returns the explicit
`fw_safe_reboot_retry` handoff to CTRL, schedules a short software reboot, and
returns **before `Update.begin()`**.

Before `ESP.restart()`, the CH422G backlight output is driven LOW and LCD reset is
driven LOW. This prevents the external panel from continuing to scan stale/random
RGB data through the software reset.

The retained-RAM request is accepted only when the next reset reason is
`ESP_RST_SW`, its magic matches, its version/SHA formats are strict and its FNV-1a
integrity checksum matches. Other reset classes ignore the handoff and boot the
normal known-good application. The actual firmware image is still authenticated
with the existing SHA-256 path; the lightweight handoff checksum is only a guard
against stale/random retained RAM.

### Headless update boot

`setup()` checks the retained-RAM handoff **before any NVS access or `lcd_init()`**.
If the validated software-reset handoff exists, it asserts the CH422G blackout
first, then reads the existing per-partition identity metadata while the display
is still inactive. In this mode it:

- initializes only the CH422G IO expander;
- holds LCD backlight LOW and LCD reset LOW;
- starts only the RS485 UART/protocol service;
- does not test/allocate PSRAM display framebuffers;
- does not initialize the RGB panel;
- does not initialize touch;
- does not initialize LVGL;
- remains in the headless RS485 service loop.

Only in this boot can the code progress past the headless gate to
`Update.begin(imageSize, U_FLASH)` and `Update.write(...)`.

Each block still enforces exact sequential offset, bounded payload size, written
length and incremental SHA-256. FW_END requires the exact expected size and
SHA-256 before `Update.end(true)`. Firmware identity metadata is stored against
the selected OTA partition; if that metadata cannot be committed, the currently
running partition is restored as boot target instead of accepting an unverifiable
image.

A verified REBOOT clears the in-memory headless update state and only then schedules
restart. If the safe updater has not started a firmware transfer within 60 seconds and is not
actively transferring/finalized, it clears headless runtime state and returns to the normal UI, preventing a
permanently black unit after an interrupted transfer.

## 3. CTRL sender handoff / retry audit

CTRL's sender still requires the peer hardware/protocol to be the approved
CTRL-TS target and requires an exact embedded native CTRL-TS size/SHA identity.
The sender state remains bounded by FW_READY/FW_ACK/FW_RESULT/REBOOT correlation,
block offsets, timeouts and retry counts.

v26.10.02.03 adds one explicit transition: while waiting for FW_READY,
`fw_safe_reboot_retry` is treated as the expected safe-updater handoff rather than
a generic updater failure. CTRL resets only its HMI transfer state, immediately
returns to HELLO discovery, and automatically starts the same embedded image when
the headless CTRL-TS reappears with the old identity.

This is important because the two-stage update deliberately contains a reboot
between the first FW_BEGIN and the actual flash transfer.

### Migration boundary for pre-.03 CTRL-TS firmware

The audit found a subtle but critical bootstrapping issue: .03 can make its own
updater safe, but it cannot retroactively change the updater code already running
on a pre-.03 CTRL-TS. Allowing .03 CTRL to send FW_BEGIN to an old receiver would
still execute that receiver's live-RGB flash implementation for the first transfer.

The release therefore adds `safe_ota=1` to the CTRL-TS HELLO identity. CTRL only
automatically self-updates a mismatched touchscreen when that capability is
present. A pre-.03 unit remains incompatible/fail-safe and reports
`manual_bootstrap` until it has been USB/Arduino-flashed to .03 once. In addition,
.03 compares every incoming target release to its running release and returns
`fw_downgrade_blocked` for an older target. This prevents a still-old CTRL from
pulling a manually recovered touchscreen back onto .01/.02 firmware. Same-version
exact-SHA repair remains allowed.

## 4. Automatic CTRL/W1P release convergence audit

No blocking firmware HTTP check is permitted in CTRL's healthy 25 ms
joystick/control loop. CTRL now accepts release change through either:

- the existing `DSP1|...|srvr_fw=<release>` display packet; or
- a dedicated `SRVR_FW|version=<release>|session=<id>` UDP beacon.

SRVR sends the dedicated CTRL beacon every 500 ms on the existing non-blocking
UDP socket. When a matched CTRL observes a different release, it invalidates its
match and enters the existing fail-closed authority/update path; HTTP/SHA/OTA
work only occurs after mismatch.

The asynchronous SRVR legacy bridge remains for old field firmware. A CTRL is
considered present for that bridge if either its high-rate control stream is
fresh or its authority/HMI status is fresh. This closes the case where SRVR can
show CTRL connected/diagnosed but an update attempt is skipped because one
specific telemetry freshness window has just expired. The bridge remains
upgrade-only and version mismatch already forces motion safe before upload.

W1P retains its independent release beacon and its existing local stop/service
inhibit before firmware-authority transition.

## 5. Calibration wizard/display reliability audit

The .02 calibration-overlay fixes are retained. While a calibration wizard is
active:

- the overlay is shown once on inactive -> active and hidden once on active ->
  inactive;
- it is created as the foreground surface and is never moved/reordered at packet
  rate;
- Travel/preset/progress and Drive/Speed/Position rendering underneath the opaque
  panel is frozen;
- parsed values are still cached and redraw normally when the wizard closes;
- labels update only when text changes; redundant explicit invalidation is not
  added after `lv_label_set_text()`.

A secondary .02 issue was found during this audit: the previous AUX Confirm latch
clear could be tied to title changes, but Joystick Calibration keeps the same
title across Left/Centre/Right. .03 tracks `(cal_kind, cal_step)` and clears the
old Confirmed latch whenever either changes. This makes each new step immediately
ready for the normal two-press Confirm interaction.

Joystick instructions are:

- `Hold Joystick Left, then press Confirm`
- `Release Joystick to Centre, then press Confirm`
- `Hold Joystick Right, then press Confirm`

The old lower `Use the assigned AUX...` description row is absent.

## 6. Preserved motion and safety invariants

The recovery changes are isolated from the winch motion architecture. Static
integration checks confirm:

- CTRL physical E-stop is AI0 only; joystick is AI1 only;
- SGM58031 channel selection/readback remains explicit and AI1 restoration is
  guaranteed after AI0 sampling attempts;
- joystick acquisition remains 25 ms / five-sample trimmed path;
- W1P retains the independent 500 ms velocity freshness watchdog;
- SRVR retains ~150 ms non-zero VEL refresh;
- W1P hard limits, dynamic/predictive soft-limit controls and service/watchdog
  stop gates remain;
- Leadshine Modbus/velocity-control architecture remains;
- CTRL-TS/firmware interface faults remain separate fail-safe flags rather than
  being mislabelled as the physical CTRL E-stop;
- new SRVR/W1P sessions still invalidate position reference and require
  calibration/re-reference before System Ready.

## 7. Build/dependency audit

The build remains pinned to:

- ESP32 Arduino core 3.3.8;
- Arduino CLI 1.5.1;
- LVGL 8.3.11;
- ESP32_Display_Panel 0.1.6;
- ESP32_IO_Expander 0.0.3;
- the pinned Waveshare_ST7262_LVGL commit recorded in CI;
- JPEGDEC 1.8.4.

The native build still compiles CTRL-TS first, measures its actual image, embeds
that exact image/version/SHA into staged CTRL, then compiles CTRL and W1P. CTRL's
unstaged source retains its hard compile guard so a fake/placeholder CTRL-TS
carrier image cannot be silently released.

## 8. Regression suite / limitations

New regression coverage includes `test_ctrl_ts_safe_update_contract.py`, which
asserts that:

- the .01/.02 RGB PCLK/restart/bounce modifications are absent;
- the normal FW_BEGIN branch returns before `Update.begin()`;
- the pending target is staged only in internal no-init RAM;
- headless selection/blackout occurs before NVS identity reads and `lcd_init()`;
- the headless branch does not call `lcd_init()` or `psramFound()`;
- flash blocks contain no LVGL/RGB operations;
- the displayed handoff contains no NVS/Preferences or `Update.*` flash write;
- handoff acceptance requires `ESP_RST_SW`, magic/format/checksum validation;
- verified reboot clears headless state;
- the no-CTRL recovery path exists.

The full local source suite passes with 357 EdgeBox integration checks and 53
build-pipeline checks, plus RS485 updater/target/retry contracts, Modbus,
Leadshine, motion, release consistency, source hygiene, Python syntax and SRVR
preflight. PySide6 runtime tests remain a CI gate because PySide6 is not installed
in the local audit environment.

### What this audit can and cannot claim

The identified source-level hazards from .01/.02 have been removed and locked by
regression tests. No known source path in .03 writes CTRL-TS flash while RGB/LVGL
is initialized. That materially reduces the risk seen on the bench.

It is **not possible to guarantee that no further issue will ever occur** from a
source-only audit. The release must still compile natively in GitHub Actions and
must be bench-tested on the actual Waveshare/EdgeBox hardware, especially the
normal -> safe-headless -> normal CTRL-TS update sequence and repeated calibration
wizard use, before machine operation is approved.
