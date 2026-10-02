HV P2P v26.10.02.03 - GITHUB READY SOURCE

PURPOSE
This is the recovery/safety successor to v26.10.02.02. It removes the low-level
CTRL-TS RGB/OTA changes introduced in .01/.02, retains the calibration-overlay
fixes, and changes CTRL-TS self-update to a display-off headless flash stage.

IMPORTANT
GitHub Actions is the authoritative native compiler. This source package does
NOT contain fabricated ESP32 application binaries, Windows executables or macOS
applications. The workflow builds CTRL-TS first, embeds that exact native image
and SHA into staged CTRL, then builds CTRL and W1P before creating matching SRVR
desktop artifacts and the Complete Release.

KEY v26.10.02.03 CHANGES
- Removed runtime RGB PCLK changes during CTRL-TS OTA.
- Removed per-block RGB panel restart/re-alignment calls.
- Removed the CI patch that changed the pinned Waveshare RGB bounce buffer from
  10 lines to 20; only the required CH422G API compatibility patch remains.
- CTRL-TS self-flash is now two-stage: show update handoff -> reboot with LCD
  backlight/reset held off -> receive/write/verify firmware without starting
  RGB/LVGL -> reboot normally.
- Added a 60 s fail-safe return from headless update mode if CTRL disappears.
- CTRL recognises the safe-update handoff and automatically resumes HELLO/update.
- Added a `safe_ota=1` capability gate. CTRL will NOT send an automatic CTRL-TS
  self-update to pre-.03 firmware, because those receivers do not have the new
  display-off updater. A one-time USB/Arduino bootstrap to .03 is required from
  .02.01/.02.02; future CTRL-TS updates are automatic again.
- CTRL-TS .03 rejects downgrade FW_BEGIN requests, so an older CTRL cannot pull a
  manually recovered .03 touchscreen back to an unsafe pre-.03 image.
- Added a dedicated 500 ms SRVR->CTRL release beacon plus the existing DSP1
  release field; legacy old-firmware OTA remains asynchronous and fail-closed.
- Retained the .02 calibration overlay fix and strengthened AUX Confirm clearing
  on each wizard kind/step transition.
- Joystick text remains `Hold Joystick Left, then press Confirm`; the lower AUX
  instruction row remains removed.

EXPECTED CTRL-TS SELF-UPDATE BEHAVIOUR
The update dashboard can show W1P and CTRL progress while CTRL-TS is running.
When CTRL-TS itself is ready to program flash, the display will intentionally go
dark during the headless write/verify stage and return after reboot. Do not treat
the deliberate dark self-flash stage as a failed update unless it exceeds the
normal transfer/recovery period or SRVR/serial diagnostics report a failure.

VERSION / BUILD IDENTITY
Application/release: 26.10.02.03
macOS short version: 26.10.2
macOS bundle build: 2610.2.3

FIRST COMMISSIONING / RECOVERY
IMPORTANT: upgrading an affected CTRL-TS from any pre-.03 firmware is deliberately
NOT automatic. The old receiver would have to execute the unsafe live-display OTA
path we are removing. Build .03 in GitHub, manually bootstrap CTRL to staged .03,
then manually bootstrap CTRL-TS to .03 once. After .03 is running, safe_ota=1
allows normal automatic CTRL-TS convergence for future releases.

Use the GitHub-produced COMPLETE_RELEASE/FIRMWARE/STAGED_SOURCE folders for any
manual commissioning flash. Read:
- INITIAL_BOOTSTRAP_v26.10.02.03.md
- NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.10.02.03.md
- CTRL_JOYSTICK_WIRING_v26.10.02.03.md
- ARDUINO_IDE_SETTINGS_v26.10.02.03.md

Bench-test CTRL-TS boot/display stability, the safe self-update handoff, all
three AUX calibration wizards, automatic SRVR-version convergence and rapid
joystick response before loaded motion commissioning.
