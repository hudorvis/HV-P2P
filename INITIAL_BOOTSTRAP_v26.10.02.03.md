# HV P2P v26.10.02.03 Initial Bootstrap / Recovery

## Build first
Upload this GitHub-ready source to the repository and let the included workflow
finish. Do not fabricate application binaries locally. Use the GitHub
`COMPLETE_RELEASE/FIRMWARE/STAGED_SOURCE` folders for manual commissioning.

## Manual commissioning settings
See `ARDUINO_IDE_SETTINGS_v26.10.02.03.md`.

Critical items:
- CTRL/W1P EdgeBox: 16 MB, QIO, PSRAM Disabled, 16M Flash menu partition; the
  sketch-local `partitions.csv` supplies the project dual-OTA table.
- CTRL-TS Waveshare: 16 MB, QIO, OPI PSRAM enabled, custom partition table.

## Required one-time recovery from pre-.03 CTRL-TS firmware

The first move from v26.10.02.01/.02 (and any earlier CTRL-TS firmware without
`safe_ota=1`) to v26.10.02.03 is intentionally **not automatic**. Letting the old
receiver perform that transfer would execute the exact live RGB/PSRAM flash path
this release removes.

1. Keep machinery unable to move / held in the normal safe service state.
2. Build v26.10.02.03 in GitHub Actions first. Do not compile an unstaged CTRL.
3. Close SRVR or otherwise keep normal network control inactive during manual
   recovery.
4. Manually flash the GitHub-produced **staged CTRL v26.10.02.03**. This CTRL
   recognises an older touchscreen but refuses to send it a self-update because it
   does not advertise `safe_ota=1`.
5. Manually USB/Arduino-flash **CTRL-TS v26.10.02.03** once from the matching
   GitHub-produced source/artifact. v26.10.02.03 itself rejects downgrade requests,
   so an older carrier cannot pull it back to a pre-.03 image.
6. Start the matching SRVR v26.10.02.03. If the manual CTRL-TS flash reports a
   bootstrap/non-matching SHA, the .03 CTRL may now safely converge it to the exact
   embedded GitHub image: the touchscreen advertises `safe_ota=1`, reboots into the
   display-off updater, and only then writes flash.
7. Bring W1P to the matching release only while stopped/braked and verify its
   existing 500 ms command watchdog/service gate.
8. Complete `NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.10.02.03.md` before loaded motion.

Do **not** use an old .01/.02 CTRL to automatically rewrite CTRL-TS during this
recovery. The one-time manual bootstrap is a deliberate safety boundary, not a
loss of the normal automatic updater.

## Normal CTRL-TS self-update behaviour after .03 is installed

- W1P/CTRL update rows may be displayed live on the CTRL-TS firmware dashboard.
- When CTRL-TS itself receives a valid update request, it shows the safe-update
  handoff and then reboots.
- On the safe updater boot, LCD reset is asserted and the backlight remains off.
  RGB/LVGL/PSRAM display framebuffers are not started.
- CTRL reconnects over RS485 and sends the exact staged CTRL-TS image.
- After size/SHA verification, CTRL-TS reboots into the new normal UI.
- If no firmware transfer starts within 60 seconds of the headless boot,
  CTRL-TS abandons the headless update state and returns to the normal UI.

The dark screen during CTRL-TS's own flash stage is intentional in .03; it is the
mechanism used to avoid the RGB corruption observed in .01/.02.

## CTRL joystick
See `CTRL_JOYSTICK_WIRING_v26.10.02.03.md`. CTRL uses the onboard EdgeBox
SGM58031: AI0 is physical E-stop status and AI1 is the joystick.

## CTRL EdgeBox <-> CTRL-TS RS485
- EdgeBox RJ45 pin 7 / RS485_A -> Waveshare A
- EdgeBox RJ45 pin 8 / RS485_B -> Waveshare B
- CTRL UART: RX18/TX17/RTS8
- Waveshare UART: RX15/TX16 automatic direction
- 115200 8N1
- Point-to-point endpoint termination as already commissioned

## W1P EdgeBox <-> Leadshine EL7-RS
Use the commissioned custom RS485 mapping, not a straight-through data cable.
Operational settings remain P05.29=4 (8N1), P05.30=6 (115200), P05.31=1, with a
drive restart after serial-setting changes.
