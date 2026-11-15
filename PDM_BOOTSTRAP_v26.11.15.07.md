# Olimex PDM bootstrap and recovery

Use the **OLIMEX ESP32-POE-ISO** with its 4 MB flash and the matching HV P2P SYS v26.11.15.07 release. The PDM sketch is under `HV_P2P_PDM_v26.11.15.07` in the source ZIP and under `FIRMWARE/STAGED_SOURCE` in the combined GitHub build.

An Olimex running the integrated dual-slot firmware can take this release from SRVR over Ethernet. Firmware before v26.11.14.01 needs its saved SRVR address to reach the update authority. A standalone PDM uses the USB procedure below.

## USB upload preserving saved settings

1. Back up the microSD card and record the PDM's current Ethernet and Wi-Fi settings, channel settings and log interval. Preserve the card's `pdm_log.csv` and `pdm_logs/` contents. Use USB with the PDM in a service window and the motion system stopped.
2. In Arduino IDE install **esp32 by Espressif Systems 3.3.8** and **ArduinoJson 7.4.2**. Open `HV_P2P_PDM_v26.11.15.07.ino` from the complete sketch folder. The other source files, `partitions.csv` and `pdm_web_assets.h` must stay beside it.
3. Select **OLIMEX ESP32-POE-ISO**, **4 MB** flash, **Minimal SPIFFS (1.9MB APP with OTA/128KB SPIFFS)** and **Erase All Flash Before Sketch Upload → Disabled**. Select the Olimex USB serial port. Upload from Arduino IDE with these settings. Use the same settings for USB recovery. The compiled partition table has two 0x1E0000-byte OTA app slots. It retains the standalone NVS partition at 0x9000 (0x5000 bytes) and OTA metadata at 0xE000 (0x2000 bytes).
4. Reconnect Ethernet and boot with the original FAT32 microSD card. The dashboard is served from the firmware at the PDM's saved Ethernet address or DHCP lease, and at its saved Wi-Fi AP address. Defaults are `http://172.20.1.110/` for Ethernet and `http://192.168.1.1/` on the AP. Existing dashboard files can remain on the card. The update uses the current PDM settings format and the existing legacy settings migrations.
5. Start the matching built SRVR. The Olimex checks the SRVR at **172.20.1.100** over Ethernet on **TCP 5760** by default. The Olimex can also use a check from a connected SRVR on the same Ethernet subnet while the factory address is in use. To select a specific authority, open the Olimex USB Serial Monitor at **115200 baud**, select **Newline** and send `SRVR_IP 172.20.1.100` with the actual SRVR Ethernet address substituted. The command saves that authority separately from the device's other settings.
6. In SRVR open **Monitoring → PDM → Settings**. Confirm or enter the PDM's actual Ethernet address under **IP Address**, then select **Apply**. Verify the saved labels, calibrated readings and retained history. Use **Web UI** to check the device dashboard and **Settings → Tools → Self Test**. With the matched release, the PDM reports **Current** after it verifies its running image. A USB build with a different binary at the same version is brought into byte-for-byte agreement with SRVR.

## USB clean install with factory defaults

### Before uploading

Record any calibration, channel names, alarm limits, logging settings and
network settings you may want to re-enter. The one-time flash erase clears
settings stored on the Olimex, including its saved SRVR address and Wi-Fi
settings. Back up the removable microSD card to preserve its voltage logs.

### Arduino IDE

1. Extract the ZIP and open `HV_P2P_PDM_v26.11.15.07/HV_P2P_PDM_v26.11.15.07.ino`. Keep the full sketch
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

- Ethernet dashboard defaults to `http://172.20.1.110/`, with subnet
  mask 255.255.0.0. The Wi-Fi AP dashboard defaults to `http://192.168.1.1/`.
- The PDM requests updates from `172.20.1.100:5760` by default. SRVR can also
  request a check from a PDM on the same Ethernet subnet. To select a
  specific SRVR address, use `SRVR_IP` as in the preserving procedure.
- In SRVR v26.11.15.07, open Monitoring → PDM → Settings and confirm the PDM Ethernet address.
  Review the channel defaults and recalibrate as needed. If the dashboard
  at this same address was used previously, use a private browser window
  for the first check or clear that dashboard's saved site data before
  opening it to avoid re-importing browser-stored legacy alarm values.
- Use an empty FAT32 microSD card if you want empty graph history. Keep the
  old card or its backup if you want to retain the logs.

## Automatic updates

PDM polls its configured SRVR over Ethernet. Starting with v26.11.14.01, SRVR also checks the PDM configured in Monitoring → PDM → Settings while the tab is closed. The PDM checks that SRVR's manifest over TCP 5760. With no explicitly saved SRVR address, it can use a temporary authority learned from the Ethernet connection on the local subnet. With a saved address, the PDM checks only that authority. After an update and reboot, SRVR requests another check so the PDM can verify the running image. The PDM verifies the release version, Olimex board target, PDM role and SHA-256 and rejects an older release. The authority endpoint uses the trusted equipment Ethernet network.

SRVR issues permission to the configured PDM Ethernet address independently of motion, calibration and E-stop state. The endpoint still returns the release and image digest expected by older integrated PDM firmware, so the installed PDM can take this revision over Ethernet. The PDM checks the permit before download and again around the SD writer pause before activation. The existing CTRL → W1P → CTRL-TS update order has its own conditions.

The PDM dashboard and API use TCP 80 on the PDM's Ethernet and Wi-Fi AP addresses. The WSI dashboard and API, SRVR firmware authority and EdgeBox service pages use TCP 5760. CTRL/W1P control uses UDP 5760. CTRL-TS firmware travels through CTRL over RS485.

The PDM Web UI mirrors the four-channel SRVR Monitoring view. Its header includes **LAN Settings** and **Wifi Settings**. Select a channel name or its **Settings** button to edit the name, alarm thresholds and measured voltage. **Settings → Tools** contains CSV export, Self Test, Refresh, Reset View and Demo Mode. The iOS bookmark path opens the same responsive dashboard.

The PDM AP needs a subnet separate from Ethernet. If the saved AP subnet overlaps Ethernet at startup or after a DHCP lease, the Olimex tries `192.168.1.1/24`, then `192.168.4.1/24` if the first address also overlaps. The running AP keeps its saved SSID and password. Open **WIFI Settings** from Ethernet to save a separate subnet. The Olimex stops Wi-Fi if it cannot configure the AP successfully.

Quit the previous SRVR before cutover. The new SRVR starts on TCP 5760 and offers the same OTA bundle on optional TCP 5000 and 5088. The November 9 PDM firmware requests TCP 5088. Nodes from v26.11.12.03 or .04 request TCP 5000. Open the port needed by the installed firmware on the equipment LAN. Legacy UDP 5000 carries migration beacons and W1P status probes. A legacy W1P reply cannot enter the motion-control path. SRVR also detects older PDM web ports 5000 and 5760, then reconnects on port 80 after the firmware update.

On a Mac, AirPlay Receiver can own TCP 5000 while SRVR runs on 5760. If a legacy node needs TCP 5000 to upgrade, temporarily turn off AirPlay Receiver and restart SRVR, or use the relevant device's manual service upload. Re-enable AirPlay after the nodes migrate. Use the PDM Ethernet address in Monitoring so the OTA permit matches.

The Monitoring → PDM view shows live connectivity, the firmware version and available update progress. Search for **PDM OTA** in the SRVR Log to follow the background update. SRVR reconnects after the PDM reboots and reloads retained history when Monitoring → PDM is open. The PDM stores readings and log settings and continues logging whenever it is powered and the card is available.

### When a PDM stays on an earlier release

The browser can open the firmware manifest as a connectivity check. The PDM must fetch the manifest from its own Ethernet connection and request permission to download and activate the image.

| SRVR Log entry | What to check |
| --- | --- |
| PDM's saved SRVR address is not assigned to this computer | Compare the listed addresses with the SRVR computer's equipment-network IPv4 address. To correct the destination, open the PDM's USB Serial Monitor at 115200 baud with Newline and send `SRVR_IP <actual SRVR Ethernet IP>`. |
| Firmware check request failed | Confirm the PDM's Ethernet IP in Monitoring → PDM → Settings. On a device with a saved SRVR IP, use its chosen authority or save the current SRVR Ethernet IP with `SRVR_IP`. |
| Awaiting a firmware request | Check the `PDM OTA:` line in the PDM's USB Serial Monitor. Verify the PDM's Ethernet link and check whether the SRVR firewall allows inbound TCP 5760 from the PDM. |
| Manifest served to the PDM | Check the next PDM OTA entry for the permit decision. The PDM's USB console also reports manifest and permit errors. |
| SRVR declined the update | Check **IP Address** under **Monitoring → PDM → Settings**. The permit and application image require the configured PDM Ethernet address. |
| Firmware permit granted or firmware image requested | Watch the firmware progress in Monitoring. If it retries, check the PDM's USB console for the download, validation, SD writer or activation result. |

## Recovery

If the PDM prints `manifest_http_-1`, it could not open its TCP connection to SRVR. For the default `172.20.1.110` Ethernet setup, if the AP also comes up as `172.20.1.1`, open the [PDM dashboard](http://172.20.1.110/) over Ethernet and choose **WIFI Settings**. Enter `192.168.1.1` for IP and Gateway and `255.255.255.0` for Subnet. Save to restart the PDM. Check that it prints the new AP IP and that its firmware request reaches SRVR. If the TCP connection still fails with separate subnets, verify inbound TCP 5760 from another device on the equipment LAN and check SRVR's incoming-connection permission on the Mac.

For a v26.11.12.07 PDM that SRVR can read but that never requests the manifest, confirm its saved SRVR Ethernet IP and access to TCP 5760. The USB `SRVR_IP` command can correct the destination. If the earlier firmware still cannot pull the update, install v26.11.15.07 once using the preserving USB procedure above. Keep the microSD card and choose **Erase All Flash Before Sketch Upload → Disabled**.

For a v26.11.09.04 PDM that is failing to fetch updates, verify that `http://<SRVR Ethernet IP>:5088/firmware/pdm/manifest` responds from the equipment LAN. If SRVR reports it could not open the port, free TCP 5088 and restart SRVR. If the manifest is reachable, check the address saved in the PDM. To set it, open Arduino Serial Monitor at 115200 baud with Newline enabled and send `SRVR_IP 172.20.1.100` using the SRVR computer's actual Ethernet address. This command saves the address without a firmware upload.

- If download stalls, Ethernet disconnects, verification fails or SRVR withdraws the permit before activation, the PDM aborts the staged update. Restore Ethernet and the configured authority and device addresses so it can retry. The previous application remains selected until a verified image is activated.
- From the equipment network, the current manifest is at `http://172.20.1.100:5760/firmware/pdm/manifest` and is also served on available legacy ports 5000 and 5088 for migration. Substitute the actual SRVR address. Compare the returned release with the running SRVR and use the Log entries above to follow the PDM's own requests.
- If the device cannot boot after activation or needs the OTA partition layout restored, use the same USB procedure with erase disabled and a known working integrated sketch. Keep the original microSD card and restore its backup if the card itself was damaged. A separately initiated factory erase would erase NVS settings.
- Use the Monitoring → PDM view and both browser access paths to verify continuity after recovery. Compare the Ethernet/AP addresses, channel names, calibration, alarms, log interval and retained samples with the pre-upload records.

[Olimex board and USB driver documentation](https://www.olimex.com/Products/IoT/ESP32/ESP32-POE-ISO/) · [Espressif OTA partition and boot selection documentation](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/system/ota.html)
