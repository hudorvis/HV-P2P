# HV P2P v26.10.02.04 deep code audit / closure

## Scope

This audit starts from the exact v26.10.02.03 release tree and the field report in
which CTRL updated but CTRL-TS remained on the firmware dashboard at:

`CTRL-TS | Restarting in safe update mode | 0%`

The attached/pasted Waveshare power-cycle log showed `rst:0x1 (POWERON)` after the
manual reboot. That proves the manual reboot itself was a power-on reset; it does
not prove that the scheduled .03 software reboot ever occurred before the manual
intervention. The .03 source explains why it could fail to occur.

Native Arduino/desktop compilation remains authoritative in GitHub Actions. Local
validation proves source/state-machine invariants but cannot prove physical panel,
RS485 timing or winch motion without the actual hardware build and bench.

## 1. Exact .03 safe-update 0% root cause

The .03 receiver handled the first displayed `FW_BEGIN` by:

1. staging the requested version/SHA in internal `__NOINIT_ATTR` RAM;
2. displaying `Restarting in safe update mode`;
3. replying `fw_safe_reboot_retry` to CTRL;
4. assigning `g_fw_safe_reboot_due_ms = millis() + 350`.

The .03 CTRL sender treated `fw_safe_reboot_retry` by resetting its firmware state,
setting `g_hmiCompatible=false`, and setting `g_lastHmiHelloTxMs=0`. Its normal HMI
service therefore immediately resumed HELLO discovery.

Because the touchscreen was still alive for up to 350 ms, it could answer that
HELLO before its scheduled reboot. CTRL saw the still-mismatched identity and
started another `FW_BEGIN`. The .03 receiver then executed the same branch again
and **replaced the reboot deadline with a new `millis()+350` value**.

On a fast RS485 link this can repeat before every deadline. The reboot is therefore
starved indefinitely and the display remains at 0% because no flash block has ever
been accepted. This is a deterministic protocol race, not an OTA-write failure.

v26.10.02.04 closes both sides:

- CTRL records `g_hmiSafeRebootHoldUntilMs = millis() + 1200` after the transition
  reply. During this interval only HMI discovery/update traffic is suppressed; the
  real-time CTRL loop continues normally.
- CTRL-TS checks `g_fw_safe_reboot_due_ms` before any restaging logic. A duplicate
  `FW_BEGIN` receives the same `fw_safe_reboot_retry` response but returns without
  touching the existing handoff or reboot deadline.
- A timing-model regression reproduces the old 100 ms rediscovery / 350 ms reboot
  starvation and asserts that the fixed deadline remains at the original 350 ms.

## 2. Headless boot audit

The .03 headless boot contained a second unnecessary risk: after software restart it
constructed a new `ESP_IOExpander_CH422G`, called `init()/begin()`, and attempted to
control LCD_BL/LCD_RST before the normal Waveshare display stack existed.

That second display/I2C bring-up is not needed. The already initialized Waveshare
runtime has a valid `expander` object before the safe restart and drives LCD_BL LOW
and LCD_RST LOW immediately before calling `ESP.restart()`. The external CH422G
retains its output latch across the ESP32 software reset.

v26.10.02.04 therefore performs **no CH422G/I2C/display initialization in the
headless boot**. The headless path intentionally leaves RGB, LVGL, PSRAM display
framebuffers, touch and the second expander path uninitialized. It starts only:

- Serial diagnostics;
- framed RS485 UART/protocol service;
- the existing OTA Update/SHA path when the validated FW_BEGIN is retried.

The live RGB application still performs no NVS or OTA flash write during the
handoff. The validated target remains in internal no-init RAM and is accepted only
after `ESP_RST_SW` with valid magic, strict version/SHA formatting and checksum.
Unexpected power/brownout/watchdog/external resets ignore that handoff.

An early reset-reason line is now printed before headless selection to make the
next hardware trace unambiguous.

## 3. Capability migration gate

`.03` advertised `safe_ota=1`. That flag can no longer be treated as sufficient,
because the level-1 implementation contains the reboot-starvation race above and
the second CH422G headless initialization.

v26.10.02.04 changes `safe_ota` into a capability level:

- 0: no safe headless updater;
- 1: `.03` first-generation headless updater (recovery-only / not auto-targeted);
- 2: `.04` corrected headless updater.

CTRL `.04` parses the numeric level, requires `>=2` for compatible identity and for
automatic CTRL-TS self-update, and reports manual bootstrap required for level 0/1.
This deliberately requires one manual USB/Arduino CTRL-TS flash from `.03` to
`.04`. After `.04` is installed, future compatible releases can use the corrected
automatic updater.

This conservative gate also prevents `.04` CTRL from trying to repair `.03` using
the very receiver implementation known to be defective.

## 4. Existing RGB safety boundary retained

The release continues to prohibit the failed `.01/.02` live-RGB OTA experiment:

- no runtime RGB PCLK changes;
- no `esp_lcd_rgb_panel_restart()` around firmware blocks;
- no firmware-specific RGB PCLK constants;
- no CI patch increasing the Waveshare bounce buffer from 10 to 20 lines;
- no `Update.begin()`/`Update.write()` from the displayed application branch.

Actual flash programming remains reachable only in the display-off/headless boot.
The 60-second no-transfer recovery still returns the device to the normal UI.

## 5. CTRL/SRVR authority and control-loop audit

The previous non-blocking authority architecture remains unchanged:

- healthy CTRL/W1P loops do not perform periodic HTTP firmware polling;
- SRVR publishes lightweight release beacons over existing UDP paths;
- a release mismatch first fails closed, then enters HTTP/SHA/OTA authority work;
- CTRL's 25 ms joystick/input loop is not blocked by the new 1.2 s HMI quiet window;
  that timer only suppresses HELLO/update traffic to CTRL-TS;
- W1P retains its independent 500 ms velocity freshness watchdog;
- SRVR retains ~150 ms non-zero VEL refresh and existing E-stop/hard-limit/soft-
  limit protections.

## 6. Calibration/display fixes retained

The .02/.03 calibration-overlay fixes remain:

- no packet-rate `lv_obj_move_foreground()` churn;
- covered Travel/Drive/Speed/Position widgets are not repainted beneath the wizard;
- redundant LVGL invalidation was removed;
- AUX Confirm state clears when the calibration kind/step advances;
- Joystick Calibration text remains `Hold Joystick Left, then press Confirm` with
  the lower AUX-description row removed.

No calibration path intentionally calls `ESP.restart()`.

## 7. Regression coverage added/updated

The v26.10.02.04 source suite now locks:

- immutable receiver safe-reboot deadline after the first FW_BEGIN;
- 1.2 s non-blocking CTRL HMI discovery hold;
- no second CH422G/I2C initialization in headless boot;
- `safe_ota=2` migration gate and rejection of level 0/1 auto-update targets;
- retained RAM software-reset/checksum gate;
- no live-display NVS/OTA write;
- no active-RGB OTA manipulation;
- exact HW/protocol/version/SHA and anti-downgrade gates;
- headless 60-second recovery;
- existing RS485 retry/finalization/idempotence contracts.

Local validation result before packaging:

- 359 EdgeBox integration checks;
- 53 build-pipeline checks;
- CTRL-TS safe-update timing/static contract;
- RS485 framing/retry/target/transport contracts;
- OTA authority, Modbus, Leadshine, joystick/motion contracts;
- release consistency, source hygiene, Python syntax and SRVR preflight;
- `ALL_SOURCE_CHECKS_PASS`.

PySide6 runtime remains a local skip when PySide6 is unavailable. GitHub Actions
native compilation and physical bench testing remain required release gates.
