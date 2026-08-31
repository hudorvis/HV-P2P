HV P2P v26.08.31.01 — COMMISSIONING SOURCE BASELINE
====================================================

STATUS
------
This is the integrated HV P2P SYS Update 4 commissioning source baseline derived from
v26.08.19.01 + v26.08.23.02 and the approved 30-Aug-2026 CTRL-TS/SRVR screenshots.

Local source/protocol result: ALL_SOURCE_CHECKS_PASS
Integration assertions: 253, plus RS485 CRC/framing, HMI retry/rollback, HMI target-gate,
carrier-generation, Leadshine Modbus, SRVR A7 wire, Python and SRVR Qt/QML preflight tests.

There is NO silent zero-byte HMI firmware placeholder in this release. The checked-in
CTRL carrier header is a compile-time #error BUILD GUARD. CTRL cannot be compiled until
a genuine native CTRL-TS application .bin has been built and embedded. The supplied
GitHub Actions workflow performs that dependency chain automatically.

This package is ready to produce the three native firmware binaries for functional bench
testing. Physical RS485, joystick, E-stop, Ethernet and Leadshine motion tests remain
mandatory before calling the system hardware-tested or production-ready.

AUTHORITATIVE HARDWARE
----------------------
CTRL — Seeed Studio EdgeBox-ESP-100
  Ethernet -> SRVR
  DI0/GPIO4 -> local 24 V NC E-stop status, HIGH healthy / LOW-open unsafe
  onboard SGM58031 AI0 -> existing 0-5 V joystick via the established 0-10 V input option
  isolated RS485 -> Waveshare CTRL-TS
  AUX1..AUX5 -> touchscreen only

W1P — Seeed Studio EdgeBox-ESP-100
  Ethernet -> SRVR
  DI0/GPIO4 -> local 24 V NC E-stop status
  isolated RS485 / Modbus RTU -> Leadshine EL7
  W1P-TS -> excluded

CTRL-TS — Waveshare ESP32-S3-Touch-LCD-7 / SKU 27078
  800x480 LVGL display/touch
  onboard automatic-direction RS485 -> CTRL
  no Ethernet role
  one initial USB flash of updater-capable firmware is required

NETWORK
-------
SRVR  172.20.1.100
CTRL  172.20.1.101
W1P   172.20.1.102
UDP control/status port 5000
CTRL-TS is RS485-only.

IMPORTANT EDGEBOX BUILD SETTING
-------------------------------
Espressif Arduino core 3.3.8 contains an Edgebox-ESP-100 board definition whose default
build.flash_size is 4 MB even though the current EdgeBox hardware is 16 MB. This project
therefore explicitly builds CTRL and W1P with FlashSize=16M. Do not compile these custom
16 MB partition maps using the stock 4 MB default.

Both EdgeBox sketches now carry a 16 MB dual-OTA partitions.csv:
  app0 0x600000
  app1 0x600000

CTRL-TS uses a conservative dual-OTA map within the first 8 MB of its 16 MB flash:
  app0 0x380000
  app1 0x380000
This leaves ample room for the firmware while keeping the updater target tightly bounded.

AUTOMATIC CTRL -> CTRL-TS UPDATE
--------------------------------
The deployed flow is:
  1. CTRL polls CTRL-TS HELLO identity: hardware + protocol + version + image SHA-256.
  2. Exact identity -> normal HMI operation.
  3. Wrong hardware or protocol -> automatic flash BLOCKED; CTRL remains fail-safe.
  4. Correct hardware/protocol but wrong version/hash -> CTRL begins update.
  5. FW_BEGIN explicitly includes target hardware/protocol, size, version, SHA and block size.
  6. CTRL-TS independently rejects FW_BEGIN if hardware/protocol target does not match.
  7. 2048-byte FW_BLOCK data is framed with CRC32, request sequence correlation and exact
     next-offset acknowledgements.
  8. CTRL-TS streams the image into the inactive OTA partition and calculates SHA-256.
  9. FW_END succeeds only on exact byte count + SHA-256.
 10. Firmware identity is committed per target OTA partition with a write-last commit marker.
 11. CTRL accepts success only if CTRL-TS echoes the exact image size + 64-char SHA-256.
 12. CTRL requests reboot and does not restore HMI compatibility until the new HELLO identity
     exactly matches the embedded carrier.

CRC32 + SHA-256 provide corruption/integrity detection. This is not signed/authenticated
secure boot; adding signed firmware would be a separate security enhancement.

BUILD THE ACTUAL TEST FIRMWARE
------------------------------
Preferred path: upload this complete source tree to GitHub and run:
  .github/workflows/firmware-build.yml

That workflow pins:
  Arduino CLI 1.5.1
  esp32:esp32 core 3.3.8
  lvgl 8.3.11
  generated lv_conf.h beside the lvgl library (16-bit colour, Arduino millis tick, required Montserrat fonts)
  ESP32_Display_Panel 0.1.6
  ESP32_IO_Expander 0.0.3
  JPEGDEC 1.8.4
  Waveshare_ST7262_LVGL 0.1 source

It then:
  A. runs all source/protocol regression tests;
  B. native-compiles CTRL-TS first;
  C. verifies its ESP image and <=0x380000 size;
  D. embeds that exact binary/SHA/version/hardware/protocol in a staged copy of CTRL;
  E. byte-verifies the generated carrier header;
  F. native-compiles CTRL with the real carrier;
  G. native-compiles W1P;
  H. enforces app-slot sizes and creates SHA-256 manifests;
  I. uploads one Native-Firmware artifact containing all binaries and the exact staged source.

The checked-in CTRL source stays guarded/unmodified, so an incomplete CTRL cannot be
mistaken for a usable binary.

INITIAL FUNCTIONAL TEST ORDER
-----------------------------
1. Obtain a successful Native-Firmware artifact from the workflow.
2. USB-flash CTRL-TS once with the matching v26.08.31.01 image.
3. Flash W1P EdgeBox and CTRL EdgeBox using the native build products/source settings.
4. Power CTRL + CTRL-TS only; verify bidirectional RS485 HELLO/update/UI before any winch motion.
5. Verify CTRL E-stop and 0-5 V joystick raw/calibrated range.
6. Connect W1P to EL7 with motor motion disabled/low-energy first; verify Modbus config/status.
7. Verify SRVR peer loss, E-stop source display, limits, brake and stop behavior.
8. Only then progress to controlled powered-motion testing.

See NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.08.31.01.md for the acceptance gates.

UI BASELINE
-----------
REFERENCE_ONLY/APPROVED_SCREENSHOTS_v26.08.30 is the locked visual authority. SRVR and
CTRL-TS share the same charcoal/grey surfaces, cyan headings, green active values and red
fault/E-stop treatment. Future work should refine, not redesign, this baseline.
