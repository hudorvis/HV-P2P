# Olimex PDM bootstrap and recovery

Use the **OLIMEX ESP32-POE-ISO** with its 4 MB flash and the matching HV P2P SYS v26.11.12.07 release. The PDM sketch is under `HV_P2P_PDM_v26.11.12.07` in the source ZIP and under `FIRMWARE/STAGED_SOURCE` in the combined GitHub build.

An Olimex already running the integrated dual-slot firmware takes this release from SRVR during an idle window. A standalone PDM uses the USB procedure below.

## USB upload preserving saved settings

1. Back up the microSD card and record the PDM's current Ethernet and Wi-Fi settings, channel settings and log interval. Preserve the card's `pdm_log.csv` and `pdm_logs/` contents. Use USB with the PDM in a service window and the motion system stopped.
2. In Arduino IDE install **esp32 by Espressif Systems 3.3.8** and **ArduinoJson 7.4.2**. Open `HV_P2P_PDM_v26.11.12.07.ino` from the complete sketch folder. The other source files, `partitions.csv` and `pdm_web_assets.h` must stay beside it.
3. Select **OLIMEX ESP32-POE-ISO**, **4 MB** flash, **Minimal SPIFFS (1.9MB APP with OTA/128KB SPIFFS)** and **Erase All Flash Before Sketch Upload → Disabled**. Select the Olimex USB serial port. Upload from Arduino IDE with these settings. Use the same settings for USB recovery. The compiled partition table has two 0x1E0000-byte OTA app slots. It retains the standalone NVS partition at 0x9000 (0x5000 bytes) and OTA metadata at 0xE000 (0x2000 bytes).
4. Reconnect Ethernet and boot with the original FAT32 microSD card. The dashboard is served from the firmware at the PDM's saved Ethernet address or DHCP lease, and at its saved Wi-Fi AP address. Defaults are `http://172.20.1.110:5760/` for Ethernet and `http://192.168.1.1:5760/` on the AP. Existing dashboard files can remain on the card. The update uses the current PDM settings format and the existing legacy settings migrations.
5. Start the matching built SRVR. The Olimex checks the SRVR at **172.20.1.100** over Ethernet on **TCP 5760**. If SRVR uses another address, open the Olimex USB serial monitor at **115200 baud**, select newline termination and send `SRVR_IP 172.20.1.100` with the actual SRVR address substituted. The new authority address is saved separately from the device's other settings.
6. In SRVR open **Monitoring → PDM**, confirm or enter the PDM's actual Ethernet address, and select **Apply**. Verify the saved labels, calibrated readings and retained history. Use **Open PDM Web UI** to check the device dashboard and its Self Test. With the matched release, the PDM reports **Current** after it verifies its running image. A USB build with a different binary at the same version is brought into byte-for-byte agreement with SRVR at the next idle window.

## USB clean install with factory defaults

### Before uploading

Record any calibration, channel names, alarm limits, logging settings and
network settings you may want to re-enter. The one-time flash erase clears
settings stored on the Olimex, including its saved SRVR address and Wi-Fi
settings. Back up the removable microSD card to preserve its voltage logs.

### Arduino IDE

1. Extract the ZIP and open `HV_P2P_PDM_v26.11.12.07/HV_P2P_PDM_v26.11.12.07.ino`. Keep the full sketch
   folder together, including partitions.csv and pdm_web_assets.h.
2. Install **esp32 by Espressif Systems 3.3.8** and **ArduinoJson 7.4.2**.
3. Select the Olimex USB serial port and the following Tools options.

| Arduino IDE option | Value |
| --- | --- |
| Board | OLIMEX ESP32-POE-ISO |
| Flash Size | 4 MB |
| PSRAM | Disabled (WROOM) |
| Partition Scheme | Minimal SPIFFS (1.9MB APP with OTA/128KB SPIFFS) |
| Erase All Flash Before Sketch Upload | Enabled for this upload |

4. Select **Verify**, then **Upload**. After the upload, set **Erase All
   Flash Before Sketch Upload** back to **Disabled** for later uploads.

### Connect after the clean install

- Ethernet dashboard defaults to `http://172.20.1.110:5760/`, with subnet
  mask 255.255.0.0. The Wi-Fi AP dashboard defaults to `http://192.168.1.1:5760/`.
- The PDM requests updates from `172.20.1.100:5760` by default. If SRVR runs
  on a different Ethernet IP, open Serial Monitor at **115200 baud** with
  **Newline** selected and send `SRVR_IP 172.20.1.100` using the actual address.
- In SRVR v26.11.12.07, open Monitoring → PDM and confirm the PDM Ethernet address.
  Review the channel defaults and recalibrate as needed. If the dashboard
  at this same address was used previously, use a private browser window
  for the first check or clear that dashboard's saved site data before
  opening it to avoid re-importing browser-stored legacy alarm values.
- Use an empty FAT32 microSD card if you want empty graph history. Keep the
  old card or its backup if you want to retain the logs.

## Automatic updates

PDM polls its configured SRVR over Ethernet independently of the open Monitoring → PDM view. The image carries the PDM role, Olimex board target and release version. Both the manifest and application image are checked. The PDM verifies the SHA-256 and rejects an older release. The authority endpoint uses the existing trusted Ethernet network.

SRVR issues permission to the configured PDM Ethernet address after three continuous seconds of idle evidence. There must be no active GOTO, calibration, battery change or motion command. A connected W1P must report fresh stopped feedback, brake applied and drive writes disabled. On an isolated bench with W1P disconnected, assert the local SRVR E-stop to permit an update. The PDM checks permission before download and again around the SD writer pause before activation. The existing CTRL → W1P → CTRL-TS update order has its own conditions.

Current PDM and WSI dashboards and APIs use TCP 5760 on the device IP. The SRVR firmware authority and EdgeBox service pages use TCP 5760. CTRL/W1P control uses UDP 5760. CTRL-TS firmware travels through CTRL over RS485.

Quit the previous SRVR before cutover. The new SRVR starts on TCP 5760 and offers the same OTA bundle on optional TCP 5000 and 5088. The November 9 PDM firmware requests TCP 5088. Nodes from v26.11.12.03 or .04 request TCP 5000. Open the port needed by the installed firmware on the equipment LAN. Legacy UDP 5000 carries migration beacons and W1P status probes. A legacy W1P reply cannot enter the motion-control path. PDM monitoring detects old dashboards on TCP 80 and 5000 until they migrate.

On a Mac, AirPlay Receiver can own TCP 5000 while SRVR runs on 5760. If a legacy node needs TCP 5000 to upgrade, temporarily turn off AirPlay Receiver and restart SRVR, or use the relevant device's manual service upload. Re-enable AirPlay after the nodes migrate. Use the PDM Ethernet address in Monitoring so the OTA permit matches.

The Monitoring → PDM view shows the device's firmware phase and available progress while connected. There is a short live-reading gap during reboot. The Monitoring → PDM view reconnects and reloads the retained history. Readings and settings are owned by the PDM, which logs whenever it is powered and the card is available.

## Recovery

For an already-running v26.11.09.04 PDM showing **Looking for SRVR**, verify that `http://<SRVR Ethernet IP>:5088/firmware/pdm/manifest` responds from the equipment LAN. If SRVR reports it could not open the port, free TCP 5088 and restart SRVR. If the manifest is reachable, check the address saved in the PDM. To set it, open Arduino Serial Monitor at 115200 baud with Newline enabled and send `SRVR_IP 172.20.1.100` using the SRVR computer's actual Ethernet address. This command saves the address without a firmware upload.

- If download stalls, disconnects, fails verification or loses its idle window before activation, the PDM aborts the staged update. Restore Ethernet and the idle conditions so it can retry. The previous application remains selected until a verified image is activated.
- If **Looking for SRVR** persists, check the saved authority address, Ethernet link, host firewall on TCP 5760 for current firmware or the relevant legacy port for older firmware and that the running SRVR includes its bundled PDM image. From the equipment network, the manifest is at `http://172.20.1.100:5760/firmware/pdm/manifest` and is also served on available legacy ports 5000 and 5088 for migration. Substitute the actual SRVR address. The status note shows whether SRVR has recently received a manifest request from the selected PDM. If **Waiting for idle** persists, check the PDM address in the Monitoring → PDM view and confirm the winch's stopped status or the isolated-bench procedure.
- If the device cannot boot after activation or needs the OTA partition layout restored, use the same USB procedure with erase disabled and a known working integrated sketch. Keep the original microSD card and restore its backup if the card itself was damaged. A separately initiated factory erase would erase NVS settings.
- Use the Monitoring → PDM view and both browser access paths to verify continuity after recovery. Compare the Ethernet/AP addresses, channel names, calibration, alarms, log interval and retained samples with the pre-upload records.

[Olimex board and USB driver documentation](https://www.olimex.com/Products/IoT/ESP32/ESP32-POE-ISO/) · [Espressif OTA partition and boot selection documentation](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/system/ota.html)
