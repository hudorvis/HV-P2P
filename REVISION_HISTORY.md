# HV P2P Revision History

## v26.10.01.03
- Built directly from v26.10.01.02 after additional CTRL joystick bench testing.
- Fixed 1-2 second periodic joystick/telemetry stalls caused by v26.10.01.02's
  blocking two-second HTTP firmware-manifest checks in the healthy CTRL/W1P main
  loops. SRVR now sends lightweight UDP release beacons; matched nodes perform no
  HTTP, and only enter the existing fail-closed HTTP/SHA/OTA path after detecting
  a release mismatch.
- Joystick Left/Centre/Right wizard completion now immediately activates and
  persists the new calibration. Setup Value/Percentage uses that calibrated range
  immediately, with the existing neutral-return motion interlock retained.
- Removed Settings and Free-D Apply/Reset footer buttons. Accepted edits auto-save;
  text editors commit on Enter/focus loss rather than each keystroke.
- Setup auto-save no longer clears CTRL receive history or reconfigures W1P for
  unrelated changes; network side effects occur only when the relevant address
  changes. Safe transactional W1P IP readdress is retained.
- Load Config now validates/applies/persists the imported full configuration
  immediately. Save Config exports the current auto-saved state.
- Added regression locks for non-blocking release beacons, calibrated percentage,
  calibration auto-commit and Settings/Free-D auto-save.
- macOS bundle build metadata advanced to `2610.1.3`.

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
