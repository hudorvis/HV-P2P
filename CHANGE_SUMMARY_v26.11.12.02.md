# HV P2P SYS v26.11.12.02

The GitHub firmware job uses Ubuntu 24.04 x64 with Python 3.12.10. The pinned Python release is available for that image. The complete-release packaging job also uses Ubuntu 24.04. ESP32 core 3.3.8, Arduino CLI 1.5.1 and the existing archive cache and retry sequence are carried forward.

## Monitoring carried forward from v26.11.12.01

SRVR now opens the PDM and WSI views under **Monitoring**. Each view has a saved IP address, a shortcut to its device web dashboard and a Log Settings dialog. The dialog reads and writes the device’s own settings.

The voltage and wind graphs show a dot, value and timestamp at the nearest displayed sample under the pointer. The PDM desktop and iOS web dashboards use the shared SRVR and CTRL-TS colour palette.

WSI communication is covered by the separate simulated WSI endpoint in the SRVR tests. See [the WSI interface](WSI_INTERFACE.md) for the contract needed by the Olimex WSI firmware.
