# HV P2P SYS v26.11.12.01 source review

Baseline HV-P2P-v26.11.09.04-GitHub.zip.

- The PDM and WSI have independent addresses, pollers, histories and log-setting transactions. The WSI client checks its role before accepting samples or writing settings. A WSI address is configured explicitly.
- SRVR reads and confirms log settings with each device. The HTTP exchanges run in monitoring workers. Settings remain device-owned.
- Hover coordinates use the same time and value scales as the drawn graph. The newest minute retains the individual samples and historical curves remain reduced for bounded rendering. Missing values break the drawn line.
- The desktop and iOS PDM pages retain their controls and routes. The refreshed assets are regenerated in the embedded firmware header.
- The controller, winch, touchscreen, motion backend, firmware authority and Actions logic match the baseline after release identifiers are normalised.
- WSI was exercised with a separate HTTP fixture. A physical sensor and WSI firmware for that sensor are pending.

See the regression log and native build and bench checklist for verification scope.
