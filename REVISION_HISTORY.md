# v26.10.06.04 — 2026-10-06

- Locked `v26.10.06.03` and changed only automatic firmware-update recovery/diagnostics plus release identity.
- Decoupled CTRL release discovery from later W1P/CTRL-TS coordinator evaluation so stage-1 `SRVR_FW` is always sent; coordinator errors fail closed with `ts_allowed=0` rather than suppressing the CTRL release beacon.
- Added exception containment around recurring firmware beacon/recovery and CTRL HMI-status handling so one coordinator error cannot silently kill automatic release discovery.
- Reduced the bounded W1P non-flashing final-stage wait to 8 s and active-update wait to 60 s while preserving preferred CTRL -> W1P -> CTRL-TS ordering.
- Added a 12 s CTRL-local recovery for a repeatedly identified, approved `safe_ota>=2` mismatched CTRL-TS after CTRL itself is exact/matched; this prevents a lost/stuck final-stage grant from requiring manual reboots.
- Split physical CTRL↔CTRL-TS RS485 activity from firmware compatibility in SRVR Setup; a live older touchscreen now shows RS485/Link Active while its firmware remains mismatched/update-required.
- Added `test_firmware_rs485_recovery_0604.py`; full historical source suite, 370 EdgeBox checks, 53 build-pipeline checks and SRVR preflight pass.
- Preserved all `.06.02` motion/UI fixes and W1P 500 ms watchdog / ~150 ms normal SRVR VEL refresh.
- macOS bundle metadata: short version `26.10.6`, build `2610.6.4`.

# v26.10.06.02 — 2026-10-06

- Locked `v26.10.06.01` as the production baseline; functional production edits are restricted to the five requested bench/UI items.
- Limit Calibration steady-motion hardening: fresh CTRL packets may renew the existing short background VEL bridge only while the physical joystick remains coherent with the command and CTRL reports no relevant safety/interface fault. Normal ~150 ms VEL cadence and the independent W1P 500 ms watchdog are unchanged; the joystick-neutral interlock remains unchanged for real safety interruptions.
- Run -> Shortcuts -> System calibration button captions shortened to **Joystick / Limit / Winch** without changing backend actions.
- Settings AUX Assign now lists **None** first while retaining all existing assignment values.
- CTRL-TS travel marker now renders smoothly from its local UI loop using bounded 180 ms signed-speed interpolation between verified HMM1 position samples. Numeric Current Position remains verified telemetry; smoothing is display-only.
- Run -> Shortcuts -> System now uses the same 31 px row height, 3 px row spacing, 5 px inner gaps and standard component fonts as the neighbouring shortcut tabs while retaining the locked label/action-column allocation.
- Added `test_bench_regression_0602.py` and updated only older assertions directly superseded by these requested UI/marker changes. Full source runner passes: 370 EdgeBox checks, all historical regressions, 53 build-pipeline checks, release/hygiene, 56-file Python syntax and SRVR preflight.
- CTRL/W1P production firmware logic remains unchanged apart from release identity. Native ESP32, PySide runtime and frozen desktop builds remain GitHub Actions gates.
- macOS bundle metadata: short version `26.10.6`, build `2610.6.2`.

# v26.10.05.11 — 2026-10-05

- Fixed the `.05.10` automatic firmware-update regression without changing the approved `.05.10` UI/calibration fixes. Root cause was a split SRVR architecture: background `SRVR_ALIVE` kept CTRL connected while `SRVR_FW`, W1P release beacons and the final CTRL-TS coordinator grant still depended on the Qt timer.
- Moved lightweight firmware discovery/order beacons into the background SRVR communications worker at 500 ms while keeping all HTTP/flash work and motion decisions in their existing fail-closed node paths.
- Added W1P network-thread firmware snapshots (STATUS plus `FW_PROGRESS`) so CTRL -> W1P -> CTRL-TS ordering no longer depends on Qt draining the W1P receive queue and remains aware of W1P during its blocking OTA download.
- Added a bounded 3 s W1P discovery grace after CTRL convergence and retained a 15 s bounded participating-W1P absence escape so normal ordering is deterministic without permanently stranding CTRL-TS.
- Made every new SRVR authority session force exact manifest/running-SHA re-verification on CTRL and W1P even for the same semantic version; exact images re-match without reflashing.
- Closed a shutdown race by re-checking `_stop_evt` under the CTRL presence TX lock so no background `SRVR_FW` can be sent after explicit `SRVR_OFFLINE`.
- Preserved the `.05.10` staged-Near calibration coordinate, Run/System row geometry and full `Practice Mode` AUX label, plus all `.05.09` updater/reboot, transactional calibration, safety arbitration and macOS communication hardening.
- Added `test_firmware_background_convergence_0511.py` and updated older brittle contracts to assert the actual preserved timing/state behavior rather than superseded debug text/local variable names.
- Full source/static/regression/preflight suite passes: 370 EdgeBox checks, all prior bench/update contracts, 53 build-pipeline checks, release/hygiene/Python syntax and SRVR preflight. Native ESP32 and frozen desktop/PySide compilation remain GitHub Actions gates.
- macOS bundle metadata used by the `.05.11` workflow: short version `26.10.5`, build `2610.5.10` (the duplicate `.05.10` CFBundleVersion was a release-metadata oversight; corrected in the next dated release).

# v26.10.05.10 — 2026-10-05

- Bench follow-up built from verified `v26.10.05.09`; all `.05.09` updater, calibration transaction, safety arbitration, background communications and watchdog protections were retained.
- Limit Calibration uses the staged Near capture as a temporary operator-facing `0.00 m` origin. CTRL-TS and the SRVR calibration popup show live distance from Near while travelling toward Far/Ref without mutating the previously valid live calibration before final Ref commit. Hardware uses raw encoder delta when available; Virtual mode uses the staged position delta.
- Run -> Shortcuts -> System controls use the same 31 px control-row height as the Limits Save/Recall/Slip controls with tighter 2 px vertical spacing, keeping all five System rows inside the Shortcuts panel.
- CTRL-TS AUX dynamic fields allow 40 characters instead of the generic 24-character display-field limit, preventing `Drive Mode | Practice Mode` from being source-truncated to `Practice Mo`. The touchscreen tile font and approved visual style are unchanged.
- Added `test_bench_regression_0510.py` plus PySide runtime assertions for calibration-relative position and full AUX label transport.
- W1P firmware/control logic remained unchanged apart from release identity. The independent 500 ms VEL watchdog, ~150 ms normal SRVR refresh, AI0/AI1 mapping, Leadshine velocity architecture, predictive/dynamic limits and hard-limit protections remained unchanged.
- macOS bundle metadata: short version `26.10.5`, build `2610.5.10`.

# v26.10.05.09 — 2026-10-05

- Rebuilt directly from the user-supplied authoritative `v26.10.05.06` source.
- Fixed CTRL-TS final-update convergence: REBOOT ACK is no longer completion;
  CTRL waits for exact target identity plus reboot proof and continues bounded
  reboot enforcement/HELLO discovery, including legacy no-preboot-id fallback.
- Rebalanced CTRL-TS AUX/travel geometry so Near/Far, REF, skate/ramp graphics and
  Preset names have separate lanes without reducing the minimum small font.
- Renamed Settings -> CTRL-TS subheading from `CTRL-TS Link` to `Link`.
- Changed uncaptured calibration values to ASCII `-`; added retry-safe touchscreen
  Cancel to Joystick and Limit Calibration.
- Made Limit Calibration transactional so Near/Far/Ref/Winch Invert commit only at
  final Ref; Cancel preserves the previous valid calibration and exits service
  motion with the neutral-return interlock intact.
- Changed W1P telemetry arbitration to validate-before-commit; malformed STATUS and
  PONG no longer create a one-frame false safety/red state while genuine stale or
  fault conditions remain fail-safe.
- Added background SRVR->CTRL liveness and short leased W1P VEL-refresh bridging to
  reduce macOS background scheduling disconnects/random calibration stops while
  preserving normal ~150 ms refresh and the unchanged W1P 500 ms watchdog.
- Corrected the GitHub C++ compile error from intermediate `.05.07/.05.08`: the
  reboot-confirmation `newBootId` is now declared in HELLO_RESP scope. Added a
  regression specifically preventing the old nested-scope form.
- Removed the unnecessary `.05.08` carrier redesign; native build/embed architecture
  is the original `.05.06` design.
- Source/static/regression/preflight suite passes locally; native ESP32 and frozen
  desktop compilation remain GitHub Actions gates.
- macOS bundle metadata: short version `26.10.5`, build `2610.5.9`.

# v26.10.05.05 — 2026-10-05

- Restored signed speed in DSP1/HMM1 transport after the `.05.04` positive-speed UI change had moved `abs()` too early into the wire packet. SRVR and CTRL-TS continue displaying Current Speed as a positive magnitude while control/transport direction stays signed.
- Updated the corresponding regression contract; no QML layout, updater coordination, W1P watchdog, Leadshine, calibration or safety behavior changed.
- macOS bundle metadata: short version `26.10.5`, build `2610.5.5`.

# v26.10.05.04 — 2026-10-05

- Bench follow-up after `.05.03` corrected calibration service-entry timing, CTRL-TS calibration presentation, post-self-update recovery, positive speed presentation, full-width travel geometry and requested SRVR shortcut/settings ordering.
- Limit/Winch service-mode transitions now transmit `SERVICE_MODE` immediately on explicit wizard open/close while retaining the convergent W1P STATUS-confirmed retry path, preventing an old limit envelope from momentarily catching the skate during recalibration.
- CTRL-TS Limit and Joystick calibration overlays now share three captured-value boxes plus a dedicated live current row (`Near / Ref / Far + Current Winch Position` and `Left / Centre / Right + Current Joystick Position`).
- Successful headless CTRL-TS OTA now has a 2.5 s autonomous verified-image reboot fallback if CTRL's final REBOOT/ACK exchange is lost; an explicit REBOOT still shortens the restart to 250 ms.
- Operator-facing Current Speed is magnitude-only on SRVR and CTRL-TS while signed internal velocity/motion direction remains unchanged.
- CTRL-TS Near↔Far track now spans the full usable 780 px travel panel width.
- Run Shortcuts mode buttons use the full available row width; Calibration Mode exposes Joystick / Limit / Winch Calibration. Settings calibration buttons are alphabetic and non-preset AUX options are alphabetized while preset action groups remain at the bottom.
- Added `test_bench_regression_0504.py` and updated older static contracts that intentionally encoded the superseded calibration/AUX ordering UI.
- W1P 500 ms velocity freshness watchdog, SRVR ~150 ms non-zero VEL refresh, Leadshine motion architecture, predictive stopping and E-stop/hard-limit protections remain unchanged.
- macOS bundle metadata: short version `26.10.5`, build `2610.5.4`.

# v26.10.05.03 — 2026-10-05

- Firmware-convergence hotfix after bench testing showed CTRL/CTRL-TS updates could require manual ESP32 reboots and CTRL-TS could remain on `.04.07` at `Waiting for CTRL` after CTRL became current.
- Moved CTRL-TS final-stage permission into the repeated lightweight `SRVR_FW` firmware-coordinator beacon (`ts_allowed`) while retaining the DSP1 mirror for compatibility. CTRL stores the grant independently of presentation traffic and invalidates stale grants on every new SRVR authority session.
- Added fresh-HELLO proactive CTRL-TS update start so an approved safe-OTA mismatched peer begins as soon as SRVR grants the final stage; the grant and HELLO no longer need to coincide in one display-packet cycle.
- Added pull-first modern OTA fallback: if an older CTRL/W1P remains mismatched for 4 s without entering its own update state, SRVR asynchronously uploads the already-verified authority image through the proven `/update/app` endpoint. This removes manual reboot as an update-start dependency while preserving upgrade-only version ordering.
- Update order remains CTRL -> W1P -> CTRL-TS; safe headless CTRL-TS self-flash, W1P 500 ms watchdog, ~150 ms SRVR non-zero VEL refresh and all Leadshine/E-stop/limit protections remain unchanged.
- Added `test_firmware_coordinator_0503.py` and updated updater regressions to enforce the new coordinator/fallback contract.
- macOS bundle metadata: short version `26.10.5`, build `2610.5.3`.

# v26.10.05.02 — 2026-10-05

- Corrected the macOS/PySide backend runtime regression for the canonical startup status priority.
- Production remains fail-safe: a fresh `WinchState` still starts with `estop_active=True` until live safety evaluation completes.
- The fresh-backend persistence test now isolates that synthetic startup safety latch before asserting `System | Uncalibrated`, so it tests non-persistent position reference state rather than external-link safety.
- Added `test_backend_status_runtime_contract_0502.py` to the normal source gate so this PySide-only fixture mismatch is caught even when PySide6 is unavailable locally.
- No W1P motion/watchdog, CTRL↔CTRL-TS transport, or approved UI behavior changed in this hotfix.
- macOS bundle metadata: short version `26.10.5`, build `2610.5.2`.

# v26.10.05.01 — 2026-10-05

- Deep SRVR↔CTRL↔CTRL-TS alignment pass after `.04.07` bench testing exposed updater ordering/progress, status flicker, low-rate touchscreen motion and Limit Calibration rendering defects.
- Added CTRL authority-update quiescing so a blocking CTRL OTA cannot begin with an outstanding touchscreen POLL/EVENT transaction; CTRL progress can now be relayed to CTRL-TS and SRVR during the transfer.
- Coordinated firmware order so CTRL must be current/fresh before W1P authority and CTRL-TS update permission; modern firmware uses SRVR authority while legacy browser-push is restricted to `<= 26.10.01.01`.
- Centralized canonical status vocabulary in SRVR (`System | Active`, `System | Uncalibrated`, `System | Battery Change Mode`, calibration states and `E-Stop | ...`) and made HMG1/HMM1 status-neutral, eliminating false Active/Uncalibrated flicker.
- Added compact HMM1 verified motion updates at ~10 Hz with 90 ms touchscreen interpolation while retaining the 4 Hz ~900-byte bulk HMI cap and single-flight RS485 arbiter.
- Increased CTRL-TS small preset/position typography to the approved Montserrat 10 minimum.
- Reworked the compact Limit Calibration Side View to an 84 px bounded viewport with fully visible tower/cable geometry while retaining the three-step Joystick-style wizard layout.
- Preserved safe headless CTRL-TS self-flash, W1P 500 ms VEL watchdog, ~150 ms SRVR non-zero VEL refresh, AI0/AI1 mapping, E-stop/hard-limit protections, predictive stopping/dynamic soft limits and Leadshine velocity architecture.
- macOS bundle metadata: short version `26.10.5`, build `2610.5.1`.

# v26.10.04.07 — 2026-10-04

- Corrected the macOS/PySide6 backend regression to match the intentional three-step Limit Calibration contract: Near, Far, then Ref & Done. The previous test still expected an obsolete fourth Done step and caused GitHub Actions to fail after a correct Ref capture.
- Hardened `calibrationNext()` so delayed/duplicate Confirm events are ignored after a calibration wizard has already closed, preventing a late CTRL-TS/SRVR event from re-entering the terminal Ref capture branch.
- No motion, RS485 scheduling, W1P watchdog, Leadshine, UI-layout, or calibration-geometry behaviour changed beyond the post-close confirmation guard.
- macOS bundle metadata: short version `26.10.4`, build `2610.4.7`.

# v26.10.04.06 — 2026-10-04

- Fixed CTRL-TS post-update state convergence: live HMI, AUX assignments, geometry, REF and presets are cached while firmware UI owns the panel and replayed immediately when normal UI returns.
- Added compact HMS1/HMG1 keepalives so state/geometry self-heal after a missed or suppressed delta.
- Fixed firmware-dashboard release so repeated inactive keepalives cannot extend the return-to-main timer indefinitely.
- Added fast CTRL firmware-authority retry during a new SRVR startup session to avoid needing a manual CTRL reboot when the SRVR beacon arrives just before the HTTP authority endpoint is ready.
- Rebuilt SRVR Limit Calibration to mirror the approved Joystick Calibration wizard: three steps (Near/Far/Ref), Side View cable-position visual, and Near/Ref/Far capture boxes.
- Limit Calibration now completes on the Ref capture and forces Battery Change Mode Off before returning to normal limit enforcement.
- Safe CTRL-TS self-flash remains intentionally headless/display-off; SRVR remains the authoritative live percentage during the CTRL-TS flash-write phase.

# v26.10.04.05 — 2026-10-04

- Fixed automatic release convergence for an already-running older CTRL: fresh CTRL `HMI_STATUS` can now schedule the background firmware push without requiring a manual CTRL/CTRL-TS reboot.
- Preserved the safe headless CTRL-TS self-updater; added a ~1.8 s `Preparing safe updater - SRVR shows self-flash progress` handoff and ~3.0 s CTRL rediscovery hold. The physical panel intentionally remains black during its own actual flash while SRVR shows exact progress.
- Standardised CTRL-TS system-state wording as `System | Active` / `System | Uncalibrated` and made operator joystick Value/Percentage display 0.0 inside the configured neutral/deadband window without changing raw calibration/motion math.
- Added live Limit Calibration feedback on SRVR and CTRL-TS: Current Position plus captured Near / Ref / Far, including observable Virtual-mode movement/capture.
- Removed AUX assignment authority from persisted CTRL `UIL1`; live SRVR AUX assignments are now authoritative across reconnect/reboot, eliminating stale `Accel Type / Goto Ref / AUX 5` labels.
- Added change-driven `HMG1` geometry transport for Near/Far/Ref, ramp fractions and preset geometry/visibility, prioritised ahead of bulk HMI telemetry while retaining the single-flight RS485 arbiter.
- Kept normal live position in the 4 Hz bulk packet; faster position/capture fields are included in priority state only while calibration is active.
- Added `test_bench_regression_0405.py` and extended runtime/static contracts for updater startup, safe handoff, status wording, joystick neutral display, Limit/Virtual calibration, AUX ownership and geometry transport.
- Preserved W1P 500 ms VEL watchdog, SRVR ~150 ms non-zero VEL refresh, E-stop/limit/Leadshine architecture and the resolved CTRL-TS AUX reboot/offline-splash behavior.
- macOS bundle metadata: short version `26.10.4`, build `2610.4.5`.

# v26.10.04.04 — 2026-10-04

- Completed the missing Run-mode Near/Far/ramp audit across SRVR and CTRL-TS. SRVR is now the single authority for effective ramp distance and normalized ramp fraction, so Distance/Percentage representations map to the same physical boundary on every display.
- Clamped effective ramp lengths to the live Near/Far span and re-synchronised metres/percentage representations after limit or ramp edits, preventing stale or impossible ramp geometry after recalibration.
- Run Top/Side, Free-D Top/Side and CTRL-TS travel bar now consume the same canonical Near/Far ramp fractions. CTRL-TS live/reference/preset marker centres align exactly with the same 0–100% Near/Far coordinates.
- Hardened Settings Battery Change and Acceleration ComboBoxes with persistent live bindings so CTRL-TS AUX/external state changes always update the visible dropdown after local ComboBox interaction.
- Reconfirmed Battery Change 5 km/h service operation, signed To Near/To Far distances outside the span, version-or-progress Firmware readouts, single CTRL-TS Firmware row, and Virtual local simulation with physical W1P STOP + Servo Enable inhibit.
- Added `test_limit_ramp_geometry_0404.py`; preserved resolved CTRL-TS AUX reboot/offline-splash behavior, W1P 500 ms watchdog and Leadshine motion architecture.
- macOS bundle metadata: short version `26.10.4`, build `2610.4.4`.

# v26.10.04.03 — 2026-10-04

- Fixed Settings Battery Change/Acceleration state convergence when changed from CTRL-TS AUX: live state now refreshes the auto-save Setup mirror and the visible selectors follow live values.
- Confirmed Battery Change as a 5 km/h service override that permits travel outside saved Near/Far limits and auto-cancels only after an outside excursion returns inside; SRVR/CTRL-TS now preserve signed `TO NEAR` / `TO FAR` values outside the span.
- Added CTRL -> SRVR firmware progress reporting and version-or-progress Firmware readouts for CTRL and W1P.
- Simplified CTRL-TS Setup firmware diagnostics to one `Firmware` readout using the same version-or-progress model.
- Corrected Virtual Position Source so SRVR simulation can run with W1P/Leadshine disconnected while any physically present W1P remains positively STOPped and software Servo Enable inhibited.
- Added `test_settings_virtual_firmware_0403.py` and updated runtime/preflight contracts.
- Preserved resolved AUX reboot/offline-splash behavior, normal Encoder safety, W1P 500 ms watchdog and Leadshine motion architecture.
- macOS bundle metadata: short version `26.10.4`, build `2610.4.3`.

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

## v26.10.05.05
- Corrected the display-speed layering exposed by the GitHub PySide runtime regression: DSP1/HMM1 retain signed speed for direction-aware transport/debug semantics, while SRVR and CTRL-TS continue rendering Current Speed as an absolute positive magnitude.
- Updated the bench regression to enforce signed transport plus magnitude-only operator presentation, preventing this contract from drifting again.
- No W1P motion/safety architecture changes.
