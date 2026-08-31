# HV P2P v26.08.31.05 — Deep Code Audit

## Result

The complete integrated source tree has been re-audited across SRVR, CTRL EdgeBox, W1P
EdgeBox and Waveshare CTRL-TS. Local source/protocol validation passes:

- **253 integration assertions**
- shared RS485 CRC32/framing host test
- HMI lost-ACK / lost-FW_RESULT / stale-sequence / rollback contract
- HMI wrong-target automatic-flash gate test
- HMI carrier generator + byte/SHA verification self-test
- Leadshine Modbus CRC contract
- actual SRVR A7 packet parser contract
- Python compile + SRVR Qt/QML/static UI/geometry/safety preflight

The source is now a **commissioning build baseline**, not a fake “flash-and-go” claim.
Native compilation is delegated to the included GitHub Actions workflow because this
container does not have the ESP32 Arduino toolchain/Waveshare libraries installed.
Real electrical/mechanical commissioning remains the final gate.

## No remaining silent firmware placeholder

The previous source baseline allowed `HV_CTRL_TS_IMAGE_AVAILABLE=false`. That has been
removed. `HV_P2P_CTRL_TS_Firmware_Image.h` is now a deliberate `#error` build guard.
An incomplete CTRL sketch therefore cannot compile at all.

The native build workflow compiles CTRL-TS first, then replaces the guard only in a staged
copy of the CTRL source using `tools/embed_ctrl_ts_firmware.py`. The helper accepts only:

- semantic version `vYY.MM.DD.RR`
- a plausible ESP application image beginning with image magic `0xE9`
- image size <= `0x380000`
- the exact shared RS485 protocol version read from the build source

It embeds the exact bytes, target hardware id, protocol, version, size and SHA-256. A
second tool reconstructs the byte array and independently verifies size/SHA/identity before
CTRL is compiled.

## New wrong-target OTA hardening

CTRL now allows automatic firmware transfer only when the HELLO peer reports both:

- hardware id `WS-ESP32S3-7`
- the exact required RS485 protocol version carried by the staged firmware identity

A wrong board or incompatible future protocol stays fail-safe and is **not flashed**.
`FW_BEGIN` also carries explicit `hw` and `proto` fields, and CTRL-TS independently rejects
an update whose target metadata does not match itself. This gives two separate target gates.

## CTRL — Seeed EdgeBox-ESP-100

- W5500 Ethernet/static IPv4/UDP 5000 retained.
- DI0/GPIO4 is the only physical CTRL switch input; NC loop is HIGH healthy / LOW-open unsafe.
- Onboard SGM58031 AI0 is used for the established 0-5 V joystick solution through the
  EdgeBox 0-10 V input option; there is no external ADS1115 dependency.
- AUX1..AUX5 are touchscreen-only over CTRL-TS RS485.
- Missing/incompatible CTRL-TS asserts the existing CTRL safety/E-stop flag.
- RS485 uses EdgeBox IO17 TX / IO18 RX / IO8 RTS hardware half-duplex.
- CTRL app0/app1 are each `0x600000` in a 16 MB custom partition table.

A key toolchain finding: Arduino-ESP32 3.3.8 defines `Edgebox-ESP-100` with a **4 MB default
flash size** even though current EdgeBox-ESP-100 hardware is 16 MB. The native workflow
therefore explicitly selects `FlashSize=16M`; relying on board defaults would be wrong for
this project.

## W1P — Seeed EdgeBox-ESP-100 / Leadshine EL7

Critical v26.08.19.01 Modbus/motion/soft-limit/peer-timeout/stop/Servo-Enable/inversion
functions remain normalized-hash locked. W1P retains 115200 8N1 Modbus, drive address 1,
EL7 config verification, DO2 Ready / DO3 Enabled / DO4 Brake / DO5 Fault, and 750 ms SRVR
peer fail-safe behavior.

W1P now also carries the same 16 MB dual-OTA app0/app1 map as CTRL so its existing browser
firmware updater is not accidentally built against a no-OTA/undersized partition layout.

## CTRL-TS — Waveshare ESP32-S3-Touch-LCD-7

- 800x480 LVGL UI and approved five-AUX layout retained.
- RS485 uses RX GPIO15 / TX GPIO16 as in Waveshare's current RS485 example/FAQ.
- CTRL remains the only bus master; CTRL-TS transmits only in direct response slots.
- Update receiver is bounded to `0x380000` bytes.
- `Update.begin(..., U_FLASH)` targets the inactive OTA app partition.
- streaming SHA-256 + exact byte count gate finalization.
- successful FW_END is idempotent for lost final responses.
- reboot is refused until a verified image exists.
- identity metadata is keyed per OTA partition with a write-last commit marker.
- metadata failure restores the currently running partition as boot target.

The CTRL-TS partition map deliberately uses only the first 8 MB (two 3.5 MiB app slots +
filesystem) even though the current SKU documentation identifies ESP32-S3N16R8. The
unused upper flash is not required by this architecture.

## SRVR / UI

The approved screenshots remain the visual authority. SRVR and CTRL-TS use the same visual
family without changing the established operator workflow. Setup uses current hardware
terminology (`Joystick AI0`, `EL7 RS485`, `CTRL-TS / FIRMWARE`) and exposes actual detected
vs required HMI firmware/update state. Free-D geometry markers are sampled from the exact
rendered cable profile so Side View points stay on the cable line.

SRVR<->CTRL/W1P wire contracts, AUX5 `0x0400`, Power/Speed naming, configuration/calibration
persistence, battery-change behavior, winch-invert semantics and Goto anti-hunt logic remain
under regression guards.

## What still requires physical proof

A successful GitHub native build removes the *compile/binary* uncertainty and produces the
real carrier. It still cannot prove electrical or mechanical behavior. Before powered motion,
bench-test:

- CTRL EdgeBox <-> Waveshare bidirectional RS485, A/B polarity and termination
- automatic same-version/bootstrap hash update and future version-mismatch update
- update retry/reboot/power-loss recovery
- CTRL joystick AI0 endpoints/centre/deadband and local E-stop
- Ethernet peer-loss behavior
- W1P <-> EL7 RS485 configuration/status/stop/brake/Servo Enable
- independent hardware E-stop/STO/brake/power isolation
- soft limits and low-speed motion before full-speed testing

Only after those gates pass should the release be described as hardware-tested/production.

## GitHub native-build fix — 31 Aug 2026

The first native CTRL-TS CI attempt stopped before compiling project code because Arduino LVGL 8.3.11 requires `lv_conf.h` beside the `lvgl` library directory. The workflow now generates this deterministically from the installed 8.3.11 template and verifies 16-bit colour, Arduino `millis()` tick source, and every Montserrat size used by CTRL-TS.

The same audit found two invalid LVGL built-in font references (`lv_font_montserrat_9` and `_11`); LVGL 8.3.11 does not provide those standard sizes. They have been replaced by the nearest built-in sizes 10 and 12 respectively, and the pipeline validator now rejects recurrence of those invalid font symbols.

## Revision v26.08.31.03 — Native compile compatibility — 2026-08-31

The second native Arduino compile reached the actual CTRL-TS source and exposed three C++/LVGL compatibility defects. These are now corrected without changing the protocol or UI design:

1. `HEX` was renamed to `HEX_DIGITS` because Arduino `Print.h` defines `HEX` as the numeric base macro `16`.
2. ESP32 Arduino Core 3.3.8 `Update.write(uint8_t*, size_t)` requires a mutable data pointer; the first correction exposed the API requirement but the following CI run showed that changing only `fw_handle_block()` to mutable was incompatible with the const `process_rs485_frame()` dispatch path.
3. LVGL 8.3.11 has no `LV_OPA_35` token. The approved 35% ramp opacity is preserved exactly with `HV_OPA_35 = 89` (35% of 255 rounded).

Warnings from the third-party Waveshare/LVGL libraries and currently unused local helper functions are non-fatal and are not the cause of the failed build.


## Revision v26.08.31.05 — CTRL-TS OTA const-safe block writer — 2026-08-31

The next native CTRL-TS compile reached the firmware dispatcher and found one remaining C++ const-correctness mismatch: `process_rs485_frame(const Frame&)` could not bind its const frame to a mutable `fw_handle_block(Frame&)`. The receiver now preserves the parser frame as const and copies only the received OTA data bytes into a dedicated bounded scratch buffer before calling ESP32 Arduino Core 3.3.8 `Update.write(uint8_t*, size_t)`. This avoids `const_cast`, keeps the dispatch API const-correct, and explicitly rejects any block larger than the scratch-buffer capacity. No RS485 wire-format, updater sequencing, UI or motion behavior changed.

## v26.08.31.05 native compiler finding

GitHub Actions reached the third-party `Waveshare_ST7262_LVGL.cpp` and failed because the
upstream Waveshare wrapper references `ESP_IO_EXPANDER_I2C_CH422G_ADDRESS`, while the
pinned `ESP32_IO_Expander 0.0.3` exposes the CH422G address variant as
`ESP_IO_EXPANDER_I2C_CH422G_ADDRESS_000`. The Waveshare wrapper itself declares
ESP32_IO_Expander 0.0.3 as a supported dependency, so this is treated as a narrow vendor
compatibility defect rather than an HV P2P application defect.

The CI workflow now runs `tools/prepare_waveshare_library.py` after cloning the wrapper.
The script verifies that the installed IO-expander library declares the `_000` symbol,
replaces only the exact legacy identifier in the vendor `.cpp`, verifies the result, and
fails closed if either side of that expected API contract has changed.
