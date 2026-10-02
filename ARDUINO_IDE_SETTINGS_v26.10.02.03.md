# Arduino IDE Commissioning Settings — v26.10.02.03

GitHub Actions remains authoritative for release compilation. These settings are
for initial/manual bench flashing only.

## CTRL / W1P Seeed EdgeBox ESP-100

- Board: **Edgebox-ESP-100**
- ESP32 Arduino core: **3.3.8** (release CI pin)
- CPU Frequency: **240 MHz (WiFi)**
- Flash Mode: **QIO 80 MHz**
- Flash Size: **16 MB (128 Mb)**
- Partition Scheme: **16M Flash (3MB APP/9.9MB FATFS)**. The sketch-local
  `partitions.csv` supplies the actual HV P2P dual-OTA layout.
- PSRAM: **Disabled**
- USB CDC On Boot: **Disabled/default**
- Upload Mode: **UART0 / Hardware CDC**
- USB Mode: **Hardware CDC and JTAG** / board default
- Upload speed: **115200** is the conservative manual commissioning setting.
- Erase All Flash Before Sketch Upload: normally **Disabled** for service flashes;
  enable only when intentionally performing a clean bootstrap/reset of NVS.

## Waveshare ESP32-S3-Touch-LCD-7

- Board: **Waveshare ESP32-S3-Touch-LCD-7** for manual IDE use, or the project's
  pinned ESP32S3 Dev Module FQBN in CI
- ESP32 Arduino core: **3.3.8**
- CPU Frequency: **240 MHz**
- Flash Mode: **QIO 80 MHz**
- Flash Size: **16 MB**
- Partition Scheme: **Custom** (uses sketch-local `partitions.csv`)
- PSRAM: **Enabled / OPI PSRAM**
- USB CDC On Boot: **Enabled** is useful for service diagnostics

If CTRL-TS reports `no mem for frame buffer`, verify PSRAM before troubleshooting
RS485.

## CTRL-TS library/build note

v26.10.02.03 deliberately restores the pinned Waveshare display port's own RGB
configuration. The release build **does not** patch its 10-line RGB bounce buffer,
does not change RGB PCLK at runtime during OTA and does not restart the RGB panel
after firmware blocks. The only Waveshare source patch in CI is the narrow
CH422G address-symbol compatibility change required by pinned
`ESP32_IO_Expander 0.0.3`.

For a manual source build intended to match release CI, use the same pinned
library/core versions. For normal commissioning, prefer the GitHub-produced
`STAGED_SOURCE` and native firmware artifacts rather than reconstructing the
release dependency set by hand.

## One-time CTRL-TS recovery from pre-.03 firmware

For a CTRL-TS currently running v26.10.02.01/.02 or any firmware that does not
advertise `safe_ota=1`, v26.10.02.03 intentionally requires one manual USB/Arduino
flash. Do not rely on the old touchscreen firmware to OTA itself into .03.

Build the release in GitHub first. Prefer the matching GitHub-produced staged
source/artifact. Bring CTRL to .03 first where practical; it will refuse to send
an unsafe update to the old touchscreen. Then flash CTRL-TS .03 once. After that,
future automatic CTRL-TS updates use the display-off headless updater.

If a clean recovery flash is specifically required, `Erase All Flash Before Sketch
Upload` may be enabled for that one CTRL-TS service flash; expect stored local NVS
metadata to be cleared. Leave it Disabled for normal service uploads.
