# HV P2P SYS v26.11.16.01

- Monitoring → Log reports confirmed CTRL, W1P, CTRL-TS, Leadshine, PDM and WSI link changes. Link-loss entries use existing evidence and a short log-only debounce. Routine W1P UDP host/network unreachable retries are omitted. Unexpected send errors and shutdown safety-send errors remain visible.
- Firmware filter collects version matches and update stages. CTRL, W1P and CTRL-TS report stage changes and progress milestones. PDM and WSI report firmware authority and download status.
- The SRVR Web UI renders to each browser's CSS viewport and device-pixel ratio and sends lossless PNG frames. The render target is bounded to 8,294,400 pixels and a 4,096-pixel edge per viewer.
