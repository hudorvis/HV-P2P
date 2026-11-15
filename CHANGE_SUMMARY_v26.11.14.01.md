# HV P2P SYS v26.11.14.01

- SRVR checks the configured PDM in the background, including when the Monitoring tab is closed. A compatible PDM checks the connected SRVR's release over Ethernet, installs its verified newer image when safe idle permits, and verifies it after reboot. A PDM using the factory address can use a responding SRVR on the local subnet. A manually saved SRVR address stays authoritative.
- **Log → Save Log** writes the timestamped text file beside the running SRVR app. On macOS this is the folder containing the .app bundle. On Windows it is the folder containing the .exe. Saves in the same second receive separate names, and SRVR displays a write failure on the Log page.
- When the PDM reports a saved SRVR address and no update request reaches this SRVR, the Log compares the saved destination with the computer's active IPv4 addresses. It lists the local addresses if they differ and points to the PDM USB Serial Monitor for the device-side error.
- The PDM keeps the safe-idle permit, Ethernet source and image integrity checks described in the bootstrap guide.
