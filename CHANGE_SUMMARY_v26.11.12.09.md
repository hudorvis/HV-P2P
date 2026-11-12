# HV P2P SYS v26.11.12.09

- PDM shows **Web UI** to the left of **Settings**. The Settings popup labels the address field **IP Address**.
- The firmware version has no hover popup. Search the SRVR Log for **PDM OTA** to see manifest requests, safe-idle decisions, image requests and reported device progress.
- The PDM updater distinguishes HTTP 409 idle holds from network, permit identity and SD writer failures. It retries promptly when the idle window closes before the image transfer begins.
- The PDM worker selects the Ethernet route when possible before requesting the manifest, checks the actual Ethernet source and retries a failed running-image read before deciding whether to reflash.
- The source checks cover the OTA worker, idle lease, image identity, logging and the PDM Monitoring UI.
