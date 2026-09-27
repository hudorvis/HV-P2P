# HV P2P v26.09.27.01 Initial Bootstrap

## Build first
Upload the complete source ZIP to the GitHub repository and let the included
workflow finish. Do not use locally fabricated application binaries. Use the
GitHub `COMPLETE_RELEASE/FIRMWARE/STAGED_SOURCE` folders for any manual Arduino
IDE commissioning flash.

## Arduino environment
- Espressif Arduino ESP32 core: 3.3.8.
- CTRL-TS libraries are pinned by GitHub Actions (LVGL 8.3.11,
  ESP32_Display_Panel 0.1.6, ESP32_IO_Expander 0.0.3, JPEGDEC 1.8.4 and the
  pinned Waveshare_ST7262_LVGL commit recorded by the workflow).
- Keep each complete staged sketch folder together, including partitions.csv and
  generated headers.

## Recommended first v26.09.27.01 commissioning order
1. Flash CTRL-TS manually from GitHub STAGED_SOURCE.
2. Flash CTRL manually from GitHub STAGED_SOURCE. The staged CTRL contains the
   exact native CTRL-TS image/hash from this same GitHub firmware build.
3. Start the matching v26.09.27.01 SRVR.
4. For W1P, use automatic SRVR convergence only if that EdgeBox already has the
   correct dual-OTA partition layout and can prove the stopped/braked service
   gate. Otherwise manually flash the GitHub W1P staged source once.
5. Bench-test with the machine unable to move before enabling motion hardware.

## CTRL EdgeBox <-> CTRL-TS Waveshare RS485
Two-wire half-duplex:
- EdgeBox RJ45 pin 7 / RS485_A -> Waveshare A.
- EdgeBox RJ45 pin 8 / RS485_B -> Waveshare B.
- In the current harness: black=A, red=B.
- EdgeBox uses RX18/TX17/RTS8; Waveshare uses RX15/TX16 with automatic direction.
- Protocol: 115200, 8N1.
- EdgeBox contains 120 ohm termination. Waveshare termination is normally enabled
  by its jumper. With power OFF and both ends connected, approximately 60 ohms
  across A/B is a useful point-to-point termination check.

## W1P EdgeBox <-> Leadshine EL7 RS485
Do NOT use a straight-through Ethernet patch cable as the data wiring.
Primary custom harness:
- EdgeBox RJ45 pin 7 / A / + -> Leadshine CN3 pin 1 / 485+.
- EdgeBox RJ45 pin 8 / B / - -> Leadshine CN3 pin 2 / 485-.

Leadshine documentation has changed between revisions. Current documentation
shows CN3 pins 1/2 and 4/5 as duplicated 485 pairs, while older documentation
used different pair labels. With power OFF, check continuity 1<->4 and 2<->5 on
the actual drive before assuming they are duplicated. Do not bridge unknown pins.

Required HV P2P EL7 communications settings:
- P05.29 = 4  (8N1)
- P05.30 = 6  (115200)
- P05.31 = 1  (Modbus slave ID 1)
Restart/power-cycle the drive after changing the serial format/baud.

If the operational link is absent while the system is safely stationary,
v26.09.27.01 W1P can perform a read-only 38400/8N2 factory-framing diagnostic.
It never writes those parameters automatically.

## EdgeBox Arduino commissioning notes
CTRL/W1P GitHub builds use the Edgebox-ESP-100 target with 16M flash, QIO,
PSRAM disabled and 240 MHz. For a one-time Arduino IDE bootstrap, if the board
menu otherwise reports a 1,310,720-byte maximum application, select a 16M
partition option that gives at least a 3 MB compile allowance while retaining
the sketch-local partitions.csv. If 921600 upload changes baud then drops the
connection, use 115200 for the commissioning flash.
