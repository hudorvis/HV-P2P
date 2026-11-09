# HV P2P SYS v26.11.09.02

- Integrates standalone PDM v26.11.09.01 on the Olimex ESP32-POE-ISO. The running SRVR release supplies the role-, target- and hash-checked PDM image over Ethernet.
- The PDM waits for a safe idle window and pauses the SD writer between operations before activation. PDM communication, firmware progress and absence are independent of motion readiness and the CTRL → W1P → CTRL-TS sequence.
- PDM serves the dashboard from flash over Ethernet and Wi-Fi AP. Saved settings, calibration and CSV files retain the standalone formats.
- SRVR Power shows four live calibrated rails, retained history, connection and stale-data status, and firmware update progress. Its default PDM address is 172.20.1.110.
- GitHub Actions adds the Olimex board target, ArduinoJson 7.4.2, the PDM partition and binary checks, and the exact PDM image in all three desktop bundles. The core installation retry behavior carries forward from SYS v26.11.08.02.

See [the bootstrap and recovery guide](PDM_BOOTSTRAP_v26.11.09.02.md) and [local verification](TEST_RESULTS_v26.11.09.02.txt).
