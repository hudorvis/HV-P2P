# Arduino IDE Commissioning Settings — v26.10.01.04

GitHub Actions remains authoritative for release compilation. These settings are for initial/manual bench flashing only.

## CTRL / W1P Seeed EdgeBox ESP-100

- Board: **Edgebox-ESP-100**
- CPU Frequency: **240 MHz (WiFi)**
- Flash Mode: **QIO 80 MHz**
- Flash Size: **16 MB (128 Mb)**
- Partition Scheme: **16M Flash (3MB APP/9.9MB FATFS)**. The EdgeBox board definition does not expose a Custom menu item; the sketch-local `partitions.csv` has higher build priority and supplies the actual dual-OTA table.
- PSRAM: **Disabled**
- USB CDC On Boot: **Disabled/default**
- Upload Mode: **UART0 / Hardware CDC**
- USB Mode: board default / Hardware CDC and JTAG
- Upload speed: 115200 is safe for commissioning; GitHub native build uses 921600.
- Erase All Flash Before Sketch Upload: **Enabled for a clean first bootstrap**. Disable later if you need to preserve NVS/network settings during a manual service flash.

## Waveshare ESP32-S3-Touch-LCD-7

- Board: **Waveshare ESP32-S3-Touch-LCD-7** (manual IDE) or the project's pinned ESP32S3 Dev Module FQBN in CI
- CPU Frequency: **240 MHz**
- Flash Mode: **QIO 80 MHz**
- Flash Size: **16 MB**
- Partition Scheme: **Custom**
- PSRAM: **Enabled** in the Waveshare board menu (the CI FQBN explicitly selects OPI PSRAM)
- USB CDC On Boot: **Enabled** is preferred for service diagnostics

If CTRL-TS reports `no mem for frame buffer`, verify PSRAM is enabled before troubleshooting RS485.
