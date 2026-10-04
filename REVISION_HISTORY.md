# v26.10.04.02 — 2026-10-04

- Bench follow-up after `.04.01` confirmed the CTRL-TS AUX reboot and immediate SRVR-offline splash fixes.
- Fixed CTRL authority OTA progress being suppressed by the normal HMI compatibility gate; firmware status now bypasses only that gate while retaining the single-flight RS485 arbiter.
- Carries CTRL/W1P firmware phase/percentage in compact HMS1 and defers CTRL-TS self-update until those external rows are inactive, keeping CTRL-TS available as their progress display.
- Shows `Preparing safe updater` for ~900 ms before the deliberate CTRL-TS headless reboot. Actual CTRL-TS self-flash remains display-off; SRVR continues to show exact percentage.
- Fixed AUX value clipping so `Practice Mode` fits in the existing tile without changing approved tile geometry.
- Replaced rectangular CTRL-TS Near/Far ramp bands with proportional wedge rendering and prioritised ramp settings in HMS1 so the visual matches SRVR semantics.
- Preserved `.04.01` AUX delivery/reboot fix, 60 ms/250 ms/300 ms HMI timing, 4 Hz bulk display cap, W1P 500 ms watchdog and the approved SRVR UI.
- macOS bundle metadata: short version `26.10.4`, build `2610.4.2`.

# v26.10.04.01 — 2026-10-04

- Fixed the remaining common CTRL-TS AUX-confirm reboot: the production UI sets `lbl_touch_debug=nullptr`, but the two-second Confirmed timeout still called `lv_label_set_text()` directly through that null pointer. The path is now null-safe and regression-locked.
- Hardened AUX local semantics so a command is not shown as Confirmed unless it actually entered the fixed retry-safe EVENT queue; queue-full leaves the tile at Confirm? for an explicit retry.
- Added end-to-end event diagnostics: CTRL reports the last accepted event ID/AUX token and SRVR logs both accepted event and resulting Drive/Battery/Acceleration state.
- Rechecked the reported Battery Change miss: AUX4 is preserved as a 16-bit A7 flag end-to-end; no source-level high-byte truncation was found. New diagnostics are intended to localize any remaining Battery-only issue after the common reboot is removed.
- Preserved the `.03.05` communications timings/safety architecture and the approved SRVR UI.
- macOS bundle metadata: short version `26.10.4`, build `2610.4.1`.

# v26.10.03.05 — 2026-10-03

- Whole-project SRVR↔CTRL↔CTRL-TS↔W1P communications audit following `.03.04` bench feedback.
- Decoupled normal CTRL-TS RS485 service from the main LVGL critical section; CTRL now restarts the POLL interval after a completed normal HMI TEXT transmission. Normal POLL cadence is 60 ms, response timeout 250 ms and late-response quiet window 300 ms.
- Reduced idle EVENT wire load while retaining full event/diagnostic packets on every real event and at least once per second.
- Replaced one-shot SRVR→W1P persistent-setting bursts with paced, STATUS-confirmed convergence. SRVR desired configuration remains authoritative and mismatches retry until W1P reports the same value.
- Reduced redundant SRVR STATUS probing of W1P to 4 Hz while retaining W1P's native 20 Hz STATUS telemetry; admitted `FW_PROGRESS` through the W1P receiver filter.
- Latched W1P software Servo-Enable inhibit across physical E-stop clear and SRVR reconnect; only SRVR's explicit neutral-verified `SW_SRVON 1` may re-enable it.
- Deferred/coalesced SRVR config notifications and aligned DSP1 build cadence to 10 Hz to reduce ComboBox/UI-thread stalls without slowing the compact priority CTRL-TS state path.
- Preserved W1P 500 ms VEL watchdog, ~150 ms SRVR non-zero VEL refresh, AI0/AI1 mapping, hard limits, predictive stopping/dynamic soft limits, approved UI and Leadshine velocity architecture.
- Added `test_end_to_end_comm_contract_0305.py`; native Arduino/frozen desktop compilation and physical reset/motion checks remain GitHub Actions/bench gates.
- macOS bundle metadata: short version `26.10.3`, build `2610.3.5`.

# v26.10.03.04 — 2026-10-03

- Bench follow-up to `.03.03` after real hardware showed SRVR dropdown latency, delayed/wrong joystick-calibration values, continued genuine CTRL-TS resets after AUX Confirm, an unnecessary update-screen flash before the intentional headless blackout, and slow SRVR-loss indication.
- Removed synchronous broad QML `stateChanged` invalidation from config handlers; gated hidden Run/Free-D cable-profile work and hidden Log filtering; cached cable profiles; throttled DSP1 construction before the expensive build.
- Joystick calibration AUX events now preserve the joystick sample from the exact CTRL datagram that carried the rising edge, so Qt/UI delay cannot substitute a later stick position.
- CTRL-TS treats compact HMS1 as a state-only render path and CTRL suppresses bulk HMI traffic for 1 s after an accepted touchscreen event. AUX debug uses a fixed buffer; EVENT diagnostics now include free heap/minimum heap/free PSRAM and SRVR logs the last values with reset reason.
- Removed the brief local CTRL-TS update-dashboard handoff; normal UI remains until the deliberate safe/headless reboot, after which black display during self-programming remains intentional and SRVR shows progress.
- Graceful SRVR shutdown now directly sends repeated `STOP` + `SW_SRVON 0` to W1P before teardown and explicitly sends `SRVR_OFFLINE` to CTRL. CTRL reports offline to CTRL-TS on the next poll and uses a 750 ms heartbeat timeout for unexpected desktop loss.
- W1P 500 ms VEL watchdog, ~150 ms SRVR non-zero VEL refresh, AI0/AI1 mapping, E-stop/hard-limit protections, predictive stopping/dynamic soft limits and Leadshine velocity architecture remain unchanged.
- macOS bundle metadata: short version `26.10.3`, build `2610.3.4`.

## v26.10.03.02
- Corrected the CTRL-TS native compile error where diagnostics referenced CTRL's `g_hmiParser` instead of CTRL-TS `g_rs485Parser`.
- Added parser-diagnostics regression coverage.

## v26.10.03.01
- Introduced single-flight CTRL↔CTRL-TS RS485 scheduling, explicit normal POLL timeout, ACK/retry-safe EVENT IDs, fixed-buffer event queue, 4 Hz bulk HMI cap and communications counters.
- Superseded by `.03.02` before bench deployment because GitHub native compilation exposed the parser-name typo.

# HV P2P Revision History

## v26.10.02.05
- Follow-up to v26.10.02.04 after bench reports of intentional-but-unexplained
  CTRL-TS black self-update periods, intermittent resets after AUX Confirm,
  calibration punctuation errors, SRVR/CTRL-TS REF mismatch and an unsupported
  SRVR status diamond.
- Kept CTRL-TS self-flash display-off/headless for RGB/PSRAM safety, but added
  CTRL `fw_pct` relay and SRVR Setup progress display so the operator can see the
  headless transfer percentage while the physical touchscreen is dark.
- Hardened AUX touch ownership: the LVGL callback now queues only a fixed uint8
  index; all confirmation/UI/String/RS485 work executes later in the Arduino main
  loop under the LVGL mutex. Removed the dormant touchscreen settings self-reboot
  timer.
- Added CTRL-TS per-boot `boot_id` + ESP `reset_reason` to HELLO, relayed by CTRL
  into SRVR HMI_STATUS and logged by SRVR on boot-ID changes.
- Corrected Joystick Calibration prompts to preserve commas and use `Press
  Confirm` for Left/Centre/Right.
- Added one SRVR-authoritative normalized Near->Far coordinate for position and REF
  and use it in both SRVR Top/Side diagrams and CTRL-TS travel markers.
- Removed the hard-coded `♢` / `◇` prefix from the SRVR top status banner.
- Preserved W1P 500 ms watchdog, ~150 ms SRVR non-zero velocity refresh, AI0/AI1
  mapping, firmware authority, predictive limits, hard limits and Leadshine motion
  architecture.
- Local source verification passes 370 EdgeBox integration checks and 53 build-pipeline checks; native compilation and physical touchscreen/reset testing remain GitHub Actions / bench gates.
- macOS bundle metadata advanced to `2610.2.5`.

## v26.10.02.04
- Bench-fix successor to v26.10.02.03 after the safe CTRL-TS updater could remain
  indefinitely at **Restarting in safe update mode | 0%**.
- Exact root cause: after `fw_safe_reboot_retry`, CTRL immediately restarted HELLO
  discovery. It could rediscover the still-running CTRL-TS before its 350 ms reboot
  deadline, send another `FW_BEGIN`, and CTRL-TS would move that deadline another
  350 ms. Repeated rediscovery could therefore postpone the reboot forever.
- Fixed both ends of the transition: CTRL now applies a non-blocking 1.2 s HMI-only
  quiet window after the safe-reboot acknowledgement, while CTRL-TS treats any
  duplicate `FW_BEGIN` during an already-scheduled safe reboot as acknowledgement
  only and never changes the original deadline.
- Removed the second CH422G/I2C initialization from the headless boot. The normal
  Waveshare runtime blanks/resets the panel immediately before software restart;
  the headless boot then leaves RGB/LVGL/PSRAM/display initialization completely
  untouched and services only RS485 + OTA.
- Raised CTRL-TS safe-update capability from `safe_ota=1` to **`safe_ota=2`**.
  `.03` is intentionally treated as a recovery-only level-1 implementation and
  `.04` CTRL will not automatically stream firmware into it. One manual CTRL-TS
  USB/Arduino flash to `.04` is required from `.03`; `.04+` releases can then use
  the corrected automatic headless updater.
- Added early reset-reason logging before headless selection so a future service
  log clearly distinguishes the deliberate software restart from power/brownout/
  watchdog reset classes.
- Added a timing-model regression test reproducing the old reboot-starvation loop,
  plus static locks for the 1.2 s sender hold, immutable receiver reboot deadline,
  no second CH422G initialization, and capability-level migration gate.
- Retains all v26.10.02.03 calibration-overlay, joystick, status, SRVR authority,
  W1P watchdog and motion-safety fixes.
- Local source validation passes 359 EdgeBox integration checks and 53
  build-pipeline checks; native compilation and physical Waveshare/RS485 testing
  remain GitHub Actions / bench gates.
- macOS bundle metadata advanced to `2610.2.4`.

## v26.10.02.02
- Follow-up to .01 after four CTRL-TS bench videos showed intermittent
  calibration-screen duplication/restart.
- Removed repeated calibration `lv_obj_move_foreground()`/hidden-state churn,
  stopped repainting covered Travel/Drive/Speed/Position widgets under the
  opaque wizard, and removed redundant explicit label invalidation.
- Simplified Joystick Calibration step text and removed the lower AUX instruction
  row.
- This revision still inherited .01's low-level RGB/OTA experiment and was
  superseded by .03 for CTRL-TS self-update reliability.

## v26.10.02.01
- Built directly from v26.10.01.04 after the 2 October CTRL-TS OTA/calibration
  bench cycle.
- Added one CTRL-TS firmware dashboard for W1P, CTRL and CTRL-TS, with phase and
  percentage per device. CTRL progress travels directly over RS485; W1P progress
  is relayed by SRVR; CTRL-TS tracks its local flash/verify state.
- Hardened the CTRL-TS RGB path during local OTA: `Update.write()` no longer runs
  under the main LVGL mutex, the dashboard is rendered before flash begins, RGB
  PCLK is reduced to 6 MHz during programming, the RGB stream is restarted after
  each block, and the pinned Waveshare build uses a 20-line bounce buffer.
- Added a visible common CTRL-TS calibration wizard for Limit, Winch and Joystick
  calibration. AUX cards remain available as the step-confirm controls and the
  previous Confirmed latch clears as soon as the wizard advances.
- Added CTRL-TS ESP reset-reason boot logging to distinguish a genuine reset from
  a UI/state transition during future bench diagnostics.
- Retained v26.10.01.04 runtime splash, status/glyph, old-release OTA bridge and
  low-latency joystick improvements.
- macOS bundle metadata advanced to short `26.10.2`, build `2610.2.1`.

## v26.10.01.04
- Built directly from v26.10.01.03 after the next CTRL/CTRL-TS bench cycle.
- Fixed AUX-assigned Limit/Winch calibration so confirmed AUX presses advance an
  already-open backend wizard instead of reopening step 1; added Joystick
  Calibration to the AUX assignment vocabulary.
- CTRL-TS returns to the original resident loading splash on runtime SRVR/CTRL
  loss and restores the main UI when connectivity returns.
- Removed unsupported Unicode decoration/square glyphs and corrected residual
  E-Stop `/` source formatting.
- Added the backwards-compatible SRVR OTA bridge for older pre-beacon CTRL/W1P
  firmware, preserving upgrade-only version ordering.
- Reduced joystick acquisition/display latency to the 25 ms / five-sample path.
- Updated the SRVR desktop icon and macOS bundle build metadata to `2610.1.4`.

## v26.10.01.03
- Built directly from v26.10.01.02 after joystick/calibration and Settings bench
  feedback.
- Removed the blocking two-second healthy-loop firmware-manifest poll that could
  stall CTRL joystick telemetry for 1-2 seconds; current firmware uses lightweight
  UDP release beacons and only enters HTTP/SHA/OTA after going fail-closed.
- Joystick Left/Centre/Right wizard completion immediately activates and persists
  the calibration; Setup Value/Percentage uses the calibrated range immediately.
- Removed Settings and Free-D Apply/Reset footer controls and changed accepted
  edits to auto-save/auto-commit semantics.
- Preserved W1P 500 ms VEL watchdog, ~150 ms SRVR non-zero VEL refresh and all
  existing emergency-stop, limit and Servo Enable protections.
- macOS bundle build metadata was `2610.1.3`.

## v26.10.01.02
- Built directly from v26.10.01.01 after first hardware bench feedback.
- Fixed automatic firmware convergence so running CTRL/W1P notice a newer SRVR
  release without requiring a controller reboot, and made SRVR reject stale
  old-release firmware-match claims.
- CTRL-TS now switches from the JPEG boot splash to the dedicated opaque update
  screen before firmware progress is rendered, with percentage redraw throttling.
- Fixed CTRL-TS E-stop formatting so `E-STOP | / W1P` cannot be produced; sources
  are reconstructed from the delimiter-safe `estop_src` field.
- macOS bundle build metadata was `2610.1.2`.

## v26.10.01.01
- Built directly from authoritative v26.09.29.06.
- Hardened SGM58031 acquisition so CTRL AI0 E-stop and AI1 joystick reads each
  explicitly select/verify their mux channel; AI1 restore is guaranteed after AI0
  sampling failures and diagnostics no longer read an unidentified active channel.
- Split physical CTRL AI0 E-stop from CTRL-TS link/firmware safety bits while
  retaining fail-safe stop behaviour.
- Made position reference session-only: SRVR always starts uncalibrated and a new
  W1P boot/session invalidates reference using W1P `BOOT_ID`. Limit Calibration or
  existing Slip/re-reference operations establish a new runtime reference.
- Unified top status priority: red safety/fault/E-stop, then yellow **System
  Un-Calibrated**, then green **System Ready**. Missing/unsafe W1P is never hidden
  by Virtual Position Source.
- Corrected installed AI1 joystick polarity at CTRL so physical Left is negative
  and Right positive; SRVR now defaults to Normal and migrates prior captured
  calibration points once.
- Added exclusive CTRL-TS runtime firmware-update screen ownership with stable
  CTRL/SRVR connection state and percentage/progress, preventing normal rendering
  from flashing over an active update.
- Added regression locks for all of the above and updated macOS bundle metadata to
  short version `26.10.1`, build `2610.1.1`.

## v26.09.29.06
- SRVR CTRL Setup labels are now **Value** and **Percentage**, with a common
  right-aligned value column.
- Added global Run -> Shortcuts -> System **Preset Names** selection: Short Names
  (`P1`...`P10`) or the existing editable Long Names. The selection is persisted
  and propagated to SRVR Top/Side views and CTRL-TS.
- Added conservative automatic joystick-centre drift compensation. It is
  runtime-only, stable-idle qualified, slow and bounded to +/-3% of calibrated
  half-span; saved calibration endpoints/centre are never silently rewritten.
- Added reaction-aware predictive stopping in SRVR and independent local W1P
  dynamic soft-limit enforcement while retaining existing hard limits.
- Reviewed Speed/Dynamic acceleration mode for incline operation: the EL7 remains
  in closed-loop velocity mode; W1P's bounded measured-speed PI correction raises
  command under load/under-speed and lowers it during over-speed without reversing
  commanded travel direction merely to brake.
- Added dedicated source regression coverage for the above changes and advanced
  the native desktop bundle build number to `2609.29.3`.

## v26.09.29.05
- CI test hotfix for the commissioned default inverted CTRL joystick direction.
- Direction-sensitive tests now validate physical direction/magnitude instead of
  assuming positive raw joystick input must produce positive motor velocity.
- No intentional runtime control/safety/RS485/UI behaviour change from .04.

## v26.09.29.04
- Final CTRL analogue mapping: **AI0/pin 14 = 5 V normally-closed E-stop status**;
  **AI1/pin 16 = APEM joystick signal**; AGND pin 12 is the common analogue return.
- SGM58031 continuous joystick channel and temporary E-stop sampling channel
  swapped accordingly; diagnostics/docs/tests updated.

## v26.09.29.03
- Joystick sampling upgraded to an 8-sample trimmed mean plus the existing light
  IIR filter.
- New/reset SRVR configuration defaults joystick Direction to Inverted.
- Added calibrated joystick percentage to CTRL Setup.
- W1P VEL freshness watchdog reduced to 500 ms and SRVR non-zero VEL refresh
  tightened to 150 ms.
- Added 5 V analogue E-stop status handling for the commissioned voltage-input
  EdgeBox arrangement (final AI0/AI1 assignment was completed in .04).

## v26.09.29.01 - v26.09.29.02
- Closed v26.09.27.01 audit/bench defects: real W1P STATUS field mismatch, stale
  PR0 trigger possibility, Modbus write exceptions, duplicate RS485 failure
  counting, best-effort stop gating, CTRL-TS session/sequence/stale-identity
  handling, stable graphical firmware progress, headless display recovery,
  full-height 800x480 Run fit and EdgeBox partition-menu compatibility while
  retaining sketch-local dual-OTA partitions.
- .02 corrected the EdgeBox FQBN partition-menu selector to the supported
  `app3M_fat9M_16MB` value; sketch-local `partitions.csv` remains authoritative.

## Earlier baseline
- **v26.08.31.01 - v26.09.04.03** — EdgeBox transition, commissioning/safety,
  locked Run/Setup UI, Virtual Position Source and cross-platform native-build
  baseline.
- **v26.09.14.x - v26.09.15.02** — SRVR-authoritative CTRL/W1P automatic OTA,
  exact SHA/identity verification, stale W1P session fail-closed handling and
  non-dirty native-build pipeline.
- **v26.09.17.01 - v26.09.17.02** — CTRL <-> CTRL-TS RS485 updater hardening:
  4096-byte UART buffers, 1024-byte blocks, conservative turnaround, bounded
  retries/idempotence, startup servicing and splash aspect/orientation handling.
- **v26.09.20.01 - v26.09.27.01** — W1P <-> Leadshine commissioning hardening,
  2.0 ms Modbus inter-frame margin, 38400 8N2 read-only factory diagnostic,
  independent velocity freshness watchdog, OTA/service safety gates and
  continued CTRL-TS automatic convergence.
