# HV P2P v26.10.02.03 Native Build and Bench Checklist

## Release gate order

1. Run the repository source suite and require `ALL_SOURCE_CHECKS_PASS`.
2. Run GitHub Actions native firmware/desktop jobs; do not substitute locally
   fabricated binaries.
3. Use only the matching Complete Release / STAGED_SOURCE / firmware artifacts.
4. Bench-test CTRL/CTRL-TS/W1P with the winch unable to move.
5. Only after the display/update and safety gates pass, continue to unloaded then
   progressively loaded motion commissioning.

## CTRL-TS recovery / boot stability

- After installing .03, power-cycle CTRL-TS at least 10 times. Every boot must
  reach the correctly scaled 800x480 splash/main UI; reject any colour cycling,
  displaced bands, repeated rows or incorrect geometry.
- Verify serial startup reports an 800x480 LCD and PSRAM present.
- Confirm `reset_reason` is recorded. If any unexpected restart occurs, preserve
  the full serial log around that boot.
- Confirm runtime SRVR loss returns to the resident splash (`Waiting for SRVR`)
  and recovery returns to the main UI without an ESP restart.

## One-time pre-.03 migration gate

Before testing normal automatic touchscreen OTA:

- With CTRL .03 and CTRL-TS still on .02.01/.02.02, confirm CTRL logs that
  automatic CTRL-TS update is **BLOCKED** because `safe_ota=1` is absent.
- Confirm SRVR shows **Manual USB bootstrap required**, not a fake successful or
  endlessly running update.
- Manually flash CTRL-TS .03 once. Confirm HELLO now contains `safe_ota=1`.
- If an older CTRL is temporarily reconnected, confirm .03 CTRL-TS returns
  `fw_downgrade_blocked` and does not erase/write an OTA partition.
- Only after this gate passes should the normal .03+ automatic self-update path
  below be tested.

## Safe CTRL-TS self-update — critical .03 acceptance

This is the most important regression test for .03.

1. Start with a matched .03 CTRL/CTRL-TS, then perform a later matched test update
   or controlled same-path update on the bench.
2. While the normal UI is still active, CTRL-TS may show the firmware dashboard
   and `Restarting in safe update mode`.
3. The screen must then deliberately go dark as CTRL-TS reboots into the headless
   updater. During this stage there must be **no** green/blue/white/black cycling,
   duplicated rows, shifted framebuffer or partial UI.
4. Serial must show the safe/headless updater target and must not show normal
   `lcd_init()`/UI startup during the flash stage.
5. CTRL must re-establish HELLO and automatically resume FW_BEGIN/FW_BLOCK/FW_END
   without requiring a manual CTRL reboot.
6. Verify exact size/SHA completion, reboot acknowledgement and a fresh normal
   HELLO/COMPATIBLE session on the new version.
7. After reboot, the main display must be correctly scaled and stable.
8. Interrupt/remove CTRL only in a safe bench test. With no transfer started, the
   headless recovery guard must return CTRL-TS to normal UI after about 60 s
   rather than leaving a permanently black screen.

**Reject the release** if CTRL-TS performs `Update.write()` while the normal RGB
UI is running, if the old 6 MHz PCLK/`esp_lcd_rgb_panel_restart()` mitigation is
present, or if CI again patches the Waveshare bounce buffer to 20 lines.

## W1P / CTRL firmware progress dashboard

- While CTRL-TS itself is in normal UI mode, trigger controlled W1P and CTRL
  updates and confirm the firmware dashboard shows their phase/percentage.
- During CTRL-TS's own headless self-flash the physical panel is intentionally
  dark; use CTRL/SRVR serial/status for transfer progress. The display returns
  after verified reboot.

## Automatic SRVR release convergence

- Run an older compatible CTRL/W1P release, then launch the newer .03 SRVR with
  no manual node reboot. Confirm the mismatch is detected and the node enters
  the fail-closed update path.
- For CTRL, verify either the normal DSP1 `srvr_fw` field or the dedicated
  `SRVR_FW` beacon invalidates an old matched release.
- Leave a matched CTRL running for several minutes: there must be no periodic
  blocking HTTP authority polling in the 25 ms control loop.
- Verify the legacy asynchronous push can start when CTRL has fresh authority/HMI
  status even if one high-rate control freshness window has just expired.
- Confirm a newer field firmware is never downgraded by the legacy bridge.

## CTRL-TS AUX calibration wizards

Repeat each wizard at least 20 times before accepting display stability.

### Joystick Calibration
- Assign `Joystick Calibration` to an AUX tile.
- First instruction must read exactly **Hold Joystick Left, then press Confirm**.
- There must be no lower `Use the assigned AUX...` description row.
- Complete Left -> Centre -> Right. Each new step must clear the previous
  Confirmed visual/latch immediately and allow the normal Confirm interaction.
- The wizard must remain correctly scaled and must not reset/reboot CTRL-TS.

### Limit Calibration / Winch Calibration
- Repeat the full wizard for each AUX assignment.
- Confirm each step advances rather than reopening step 1.
- Confirm no repeated/duplicated Drive/Speed/Position rows appear under/after the
  wizard and no unexpected boot splash occurs.

## CTRL analogue / joystick bench

- AI0/pin 14 = physical normally-closed 5 V E-stop status only.
- AI1/pin 16 = joystick signal only.
- AGND/pin 12 = common analogue ground.
- Confirm the commissioned 249-ohm current-input shunts are removed for voltage
  input use.
- Confirm E-stop is healthy high and fails unsafe on press/open/input fault.
- Confirm SGM58031 at 0x48 and no analogue fault.
- Run joystick Left/Centre/Right calibration and verify Value/Percentage maps the
  captured range to approximately -100 / 0 / +100%.
- Rapidly step joystick centre -> full travel repeatedly. The SRVR readout must
  update promptly and continuously; reject periodic 1-2 s stalls.

## Safety/watchdog regression

- Verify W1P independent VEL freshness watchdog remains 500 ms.
- Verify SRVR non-zero VEL refresh remains ~150 ms.
- Interrupt SRVR command traffic only under safe bench conditions and confirm W1P
  stops/inhibits independently.
- Verify CTRL physical E-stop, W1P E-stop/internal safety, CTRL-TS link fault and
  firmware-authority mismatch all fail safe with correct source/status reporting.
- After every new SRVR/W1P power session, verify system remains yellow
  `System Un-Calibrated` until Limit Calibration or a known Slip/re-reference is
  deliberately completed.

## Predictive limits / Leadshine / loaded-motion commissioning

Only after all display/update/safety gates above pass:

- Verify Near/Far hard limits in both directions.
- Commission predictive/dynamic soft-limit taper from low speed upward.
- Verify W1P local protection still acts if SRVR updates are interrupted.
- Confirm Leadshine communication at commissioned 115200 8N1 slave 1.
- Verify failed Modbus writes cannot trigger stale PR0 movement.
- Test Speed/Dynamic regulation first unloaded/light-load, then progressively
  increase intended slope/payload while monitoring drive/regeneration limits.

## Release acceptance

Do not treat the source ZIP alone as a proven machine release. Archive:

- successful GitHub Actions native build logs;
- Complete Release SHA-256/checksum manifests;
- CTRL/CTRL-TS serial logs for safe headless OTA;
- repeated calibration-wizard video/bench results;
- E-stop/watchdog/limit commissioning records;
- Leadshine and loaded-motion acceptance results.
