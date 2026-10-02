# HV P2P v26.10.02.04 change summary

## Why this revision exists

v26.10.02.03 successfully removed the unsafe live-RGB flash path, but bench testing
found a deterministic handoff race: CTRL-TS could sit forever at **Restarting in
safe update mode | 0%** and never enter its display-off updater.

## Exact .03 failure path

1. CTRL sends `FW_BEGIN`.
2. Displayed CTRL-TS stages the RAM-only safe-update handoff, replies
   `fw_safe_reboot_retry`, and schedules `ESP.restart()` for 350 ms later.
3. CTRL receives that reply, immediately drops back to HELLO discovery.
4. Before 350 ms expires, the still-running CTRL-TS answers HELLO with its old
   image identity.
5. CTRL immediately sends another `FW_BEGIN`.
6. `.03` CTRL-TS restages the request and resets its reboot deadline to
   `millis()+350` again.
7. Fast repetition can postpone the reboot indefinitely, so progress never moves
   beyond 0%.

This is a protocol timing bug, not a failed firmware block write.

## v26.10.02.04 fix

The transition is now protected at both ends:

- CTRL applies a **1.2 s non-blocking HMI discovery hold** after receiving
  `fw_safe_reboot_retry`. The 25 ms joystick/control loop continues normally;
  only CTRL-TS discovery/update traffic is paused.
- CTRL-TS records the first 350 ms reboot deadline once. Any duplicate `FW_BEGIN`
  while that deadline is pending receives the same transition reply but cannot
  restage the handoff or move the deadline.
- The headless boot no longer creates a second `ESP_IOExpander_CH422G` instance or
  initializes an I2C/display path. The already-running Waveshare instance blanks
  LCD_BL/LCD_RST before restart; the safe boot then initializes only serial/RS485
  and OTA services, with no RGB/LVGL/PSRAM/touch bring-up.
- An early reset-reason line is emitted before safe-headless selection for clearer
  service diagnostics.

## Migration safety: safe_ota=2

`.03` advertised `safe_ota=1`, but that receiver still contains the reboot race and
second-CH422G headless initialization. `.04` therefore raises the capability to
**`safe_ota=2`**. CTRL `.04` will not automatically self-update a level-0 or level-1
CTRL-TS.

For the currently affected `.03` touchscreen, perform **one manual USB/Arduino
flash to `.04`**. After `.04` is running, future CTRL-TS releases can use the fixed
automatic display-off/headless updater.

## Preserved behaviour

- no flash/NVS write while the normal RGB/LVGL display is active;
- no runtime RGB PCLK manipulation or per-block RGB restart;
- upstream Waveshare bounce-buffer configuration retained;
- exact HW/protocol/version/SHA target gates and anti-downgrade logic;
- 60 s safe-mode recovery timeout;
- calibration overlay reliability fixes and Joystick Calibration wording;
- CTRL AI0 E-stop / AI1 joystick mapping and low-latency sampling;
- W1P 500 ms velocity watchdog and existing motion/limit/E-stop protections.

## Validation

Local source suite: **ALL_SOURCE_CHECKS_PASS** after 359 EdgeBox integration checks,
53 build-pipeline checks, safe-update timing/static contracts, RS485/OTA/Modbus/
Leadshine/motion contracts, source hygiene, Python syntax and SRVR preflight.

Native Arduino/desktop compilation remains authoritative in GitHub Actions and the
corrected CTRL-TS updater still requires physical bench acceptance.

macOS bundle build: `2610.2.4`
