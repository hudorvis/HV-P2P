# Arduino IDE Commissioning Settings — v26.10.05.04

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

v26.10.05.04 deliberately restores the pinned Waveshare display port's own RGB
configuration. The release build **does not** patch its 10-line RGB bounce buffer,
does not change RGB PCLK at runtime during OTA and does not restart the RGB panel
after firmware blocks. The only Waveshare source patch in CI is the narrow
CH422G address-symbol compatibility change required by pinned
`ESP32_IO_Expander 0.0.3`.

For a manual source build intended to match release CI, use the same pinned
library/core versions. For normal commissioning, prefer the GitHub-produced
`STAGED_SOURCE` and native firmware artifacts rather than reconstructing the
release dependency set by hand.

## One-time CTRL-TS recovery from v26.10.02.03

For the current recovery, manually USB/Arduino flash CTRL-TS from `.03` to `.04`.
`.03` advertises `safe_ota=1`; `.04` requires `safe_ota=2` because the level-1
handoff can starve its scheduled reboot. Do not rely on `.03` to self-install `.04`.

Build `.04` in GitHub first and use the matching GitHub-produced artifact/source.
Bring CTRL to `.04` first where practical; CTRL `.04` will deliberately report a
level-1 touchscreen as manual-bootstrap-required rather than invoking its old
updater. Flash CTRL-TS `.04` once. After that, automatic headless updates resume.

If a clean recovery flash is specifically required, `Erase All Flash Before Sketch
Upload` may be enabled for that one service flash; expect stored local NVS metadata
to be cleared. Leave it Disabled for normal service uploads.

## Manual CTRL-TS flash and exact-image synchronization

A manual Arduino IDE flash does not write HV P2P's per-partition trusted firmware
SHA metadata. Therefore, even when the manually flashed CTRL-TS reports the same
release version, a matched CTRL can legitimately perform one automatic
same-version update to install/verify the exact GitHub-staged image and SHA.

During that exact-image synchronization the CTRL-TS display intentionally goes
black in the headless flash phase. v26.10.05.04 relays the transfer percentage to
SRVR Setup so progress can be monitored there. After the verified reboot, the
reported SHA should match CTRL's embedded required image and the repeat update
should stop.
