# HV P2P v26.10.02.05 change summary

## Why this revision exists

v26.10.02.04 established the display-off/headless CTRL-TS self-updater, but the
next bench cycle exposed several independent operator/display issues:

1. CTRL-TS deliberately went black for its own flash programming but SRVR did not
   expose useful transfer percentage during that headless period.
2. Repeated AUX confirmations (Joystick Calibration, Drive Mode, Battery Change)
   were followed by intermittent CTRL-TS restarts on hardware.
3. Joystick Calibration punctuation was altered from comma to slash in the
   SRVR->CTRL-TS text packet.
4. SRVR Top/Side REF position and the CTRL-TS travel-bar REF marker could disagree.
5. SRVR's top status banner prepended an unsupported diamond character.

## CTRL-TS self-update display behaviour

The black screen during CTRL-TS's **own** flash write is intentional and remains
part of the safe updater. The Waveshare RGB/LVGL/PSRAM stack is not started in the
headless update boot, so the panel cannot safely render a live percentage while
its own application partition is being programmed.

v26.10.02.05 improves operator visibility without weakening that boundary:

- CTRL now reports CTRL-TS update phase and percentage in `HMI_STATUS`.
- SRVR parses and exposes that percentage, including the safe-reboot and headless
  transfer phases.
- Setup now shows the percentage beside the CTRL-TS update state while the panel
  itself is intentionally dark.
- CTRL-TS continues to show W1P/CTRL firmware progress while its normal display is
  active; only its own self-flash phase goes dark.

A manual Arduino flash can legitimately be followed by one same-version automatic
CTRL-TS synchronization: a manual flash has no trusted per-partition staged SHA
metadata, so CTRL still requires the exact GitHub-staged image identity before it
marks the touchscreen compatible. This exact-image repair preserves the existing
version/SHA safety contract.

## AUX-confirm / reboot hardening

There is no intended `ESP.restart()` path for Joystick Calibration, Drive Mode,
Battery Change, or ordinary AUX confirmation. The remaining structural risk was
that the Waveshare LVGL callback directly executed AUX state/UI/protocol work,
including dynamic `String` operations, inside the separate LVGL task.

v26.10.02.05 changes that boundary:

- the LVGL AUX callback now performs only a fixed-size, heap-free queue operation;
- all AUX confirmation state changes, tile updates and RS485 event creation are
  executed later by the Arduino main loop while it owns the LVGL mutex;
- the dormant CTRL-TS settings self-restart timer is removed so an ordinary UI
  settings action cannot schedule a touchscreen reboot;
- CTRL-TS now generates a per-boot `boot_id` and reports `reset_reason` in HELLO;
- CTRL relays both fields to SRVR, and SRVR logs any boot-ID change.

This means a future physical reset is no longer ambiguous: the SRVR/CTRL logs can
show that a real new boot occurred and identify the ESP reset class. Physical
bench testing is still required to prove whether the observed resets were caused
by the old callback path or another board-level issue.

## Joystick Calibration wording

The slash was caused by SRVR's generic display-field sanitizer replacing commas
with `/`. Packed preset-list fields still require comma sanitization, but a
standalone calibration instruction does not. Calibration instructions now bypass
that replacement and are locked to:

- `Hold Joystick Left, then Press Confirm`
- `Release Joystick to Centre, then Press Confirm`
- `Hold Joystick Right, then Press Confirm`

## Canonical position / REF mapping

SRVR now computes one authoritative normalized Near->Far fraction for both the
current position and REF point. Those exact fractions are:

- exposed to the SRVR Run Top/Side views;
- transmitted in the DSP1/HMI1 packet as `pos_frac` and `ref_frac`;
- consumed directly by CTRL-TS for its travel-bar position and REF markers.

Both displays therefore share the same horizontal coordinate rather than each
independently re-deriving a fraction from absolute/relative values. Legacy packet
fallback remains in CTRL-TS for compatibility.

## SRVR status glyph

The leading `♢` / `◇` characters were explicitly hard-coded in `Main.qml`.
They have been removed. The top status now renders `backend.bannerText` directly,
for example `E-Stop | W1P`.

## Preserved safety / architecture

- CTRL AI0 = physical E-stop; AI1 = joystick.
- W1P independent 500 ms velocity freshness watchdog.
- SRVR non-zero velocity refresh around 150 ms.
- predictive stopping / dynamic soft limits / hard-limit protections.
- fail-closed firmware authority and exact CTRL-TS HW/protocol/version/SHA gates.
- display-off/headless CTRL-TS self-flash; no live RGB/PSRAM flash writes.
- no runtime RGB PCLK manipulation, per-block RGB restart or 20-line bounce-buffer
  patch.

## Validation

Current local source verification passes **370 EdgeBox integration checks**, **53 build-pipeline checks**, the dedicated CTRL-TS safe-update contract, RS485 retry/target/transport contracts, OTA authority, Modbus/Leadshine, motion/joystick, source-hygiene, Python-syntax and SRVR preflight checks, ending in `ALL_SOURCE_CHECKS_PASS`.

The complete source suite is run again from a clean extraction of the final ZIP. Native Arduino and desktop compilation remain GitHub Actions gates; physical AUX/reset and Waveshare update behaviour remain bench gates.

macOS bundle build: `2610.2.5`
