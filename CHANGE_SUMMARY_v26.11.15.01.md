# HV P2P SYS v26.11.15.01

- **Log → Save Log** writes the timestamped text file beside the running SRVR app. If the write fails, the Log page shows the attempted folder and filesystem error. For a macOS App Translocation path it explains why that location is read-only.
- **Choose Folder** in the error dialog retries in a folder selected for that export. The next **Save Log** uses the app folder again.
- The PDM bootstrap guide identifies v26.11.14.01 as the first release that can respond to SRVR-initiated firmware checks over Ethernet.
- The PDM keeps the safe-idle permit, Ethernet source and image integrity checks described in the bootstrap guide.
