# Olimex PDM bootstrap and recovery

Use the **OLIMEX ESP32-POE-ISO** with its 4 MB flash and the matching HV P2P SYS v26.11.09.03 release. The PDM sketch is under `HV_P2P_PDM_v26.11.09.03` in the source ZIP and under `FIRMWARE/STAGED_SOURCE` in the combined GitHub build.

An Olimex already running the integrated dual-slot firmware takes this release from SRVR during an idle window. A standalone PDM uses the USB procedure below.

## One-time USB upload

1. Back up the microSD card and record the PDM's current Ethernet and Wi-Fi settings, channel settings and log interval. Preserve the card's `pdm_log.csv` and `pdm_logs/` contents. Use USB with the PDM in a service window and the motion system stopped.
2. In Arduino IDE install **esp32 by Espressif Systems 3.3.8** and **ArduinoJson 7.4.2**. Open `HV_P2P_PDM_v26.11.09.03.ino` from the complete sketch folder. The other source files, `partitions.csv` and `pdm_web_assets.h` must stay beside it.
3. Select **OLIMEX ESP32-POE-ISO**, **4 MB** flash, **Minimal SPIFFS (1.9MB APP with OTA/128KB SPIFFS)** and **Erase All Flash Before Sketch Upload → Disabled**. Select the Olimex USB serial port. Upload from Arduino IDE with these settings. Use the same settings for USB recovery. The compiled partition table has two 0x1E0000-byte OTA app slots. It retains the standalone NVS partition at 0x9000 (0x5000 bytes) and OTA metadata at 0xE000 (0x2000 bytes).
4. Reconnect Ethernet and boot with the original FAT32 microSD card. The dashboard is served from the firmware at the PDM's saved Ethernet address or DHCP lease, and at its saved Wi-Fi AP address. Defaults are `http://172.20.1.110/` for Ethernet and `http://192.168.1.1/` on the AP. Existing dashboard files can remain on the card. The update uses the current PDM settings format and the existing legacy settings migrations.
5. Start the matching built SRVR. The Olimex checks the SRVR at **172.20.1.100** over Ethernet on **TCP 5088**. If SRVR uses another address, open the Olimex USB serial monitor at **115200 baud**, select newline termination and send `SRVR_IP 172.20.1.100` with the actual SRVR address substituted. The new authority address is saved separately from the device's other settings.
6. In SRVR open **Power**, confirm or enter the PDM's actual Ethernet address, and select **Apply**. Verify the saved labels, calibrated readings and retained history. Use **Open PDM Web UI** to check the device dashboard and its Self Test. With the matched release, the PDM reports **Current** after it verifies its running image. A USB build with a different binary at the same version is brought into byte-for-byte agreement with SRVR at the next idle window.

## Automatic updates

PDM polls its configured SRVR over Ethernet independently of the open Power tab. The image carries the PDM role, Olimex board target and release version. Both the manifest and application image are checked. The PDM verifies the SHA-256 and rejects an older release. The authority endpoint uses the existing trusted Ethernet network.

SRVR issues permission to the configured PDM Ethernet address after three continuous seconds of idle evidence. There must be no active GOTO, calibration, battery change or motion command. A connected W1P must report fresh stopped feedback, brake applied and drive writes disabled. On an isolated bench with W1P disconnected, assert the local SRVR E-stop to permit an update. The PDM checks permission before download and again around the SD writer pause before activation. The existing CTRL → W1P → CTRL-TS update order has its own conditions.

The Power tab shows the device's firmware phase and available progress while connected. There is a short live-reading gap during reboot. The Power tab reconnects and reloads the retained history. Readings and settings are owned by the PDM, which logs whenever it is powered and the card is available.

## Recovery

- If download stalls, disconnects, fails verification or loses its idle window before activation, the PDM aborts the staged update. Restore Ethernet and the idle conditions so it can retry. The previous application remains selected until a verified image is activated.
- If **Looking for SRVR** persists, check the saved authority address, Ethernet link, host firewall on TCP 5088 and that the running SRVR includes its bundled PDM image. If **Waiting for idle** persists, check the PDM address in the Power tab and confirm the winch's stopped status or the isolated-bench procedure.
- If the device cannot boot after activation or needs the OTA partition layout restored, use the same USB procedure with erase disabled and a known working integrated sketch. Keep the original microSD card and restore its backup if the card itself was damaged. A separately initiated factory erase would erase NVS settings.
- Use the Power tab and both browser access paths to verify continuity after recovery. Compare the Ethernet/AP addresses, channel names, calibration, alarms, log interval and retained samples with the pre-upload records.

[Olimex board and USB driver documentation](https://www.olimex.com/Products/IoT/ESP32/ESP32-POE-ISO/) · [Espressif OTA partition and boot selection documentation](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/system/ota.html)
