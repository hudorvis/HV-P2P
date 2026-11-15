# HV P2P SYS v26.11.15.03

- PDM updates start automatically for the configured Ethernet device, independently of motion and E-stop state. The existing permit endpoint still verifies the selected peer and image. The PDM verifies the target, version and image and flushes SD before activating it.
- The same SRVR authority supports optional WSI images when WSI firmware is available. It verifies and serves each monitoring role at its configured IP.
- The embedded PDM Web UI matches the SRVR Monitoring PDM view, with LAN Settings and Wifi Settings to the left of Web UI and Settings. The dashboard retains calibration, names, alarms, logging and history. CSV, Self Test, view reset, refresh and Demo Mode are under Settings → Tools.
