# HV P2P SYS v26.11.09.04 initial and recovery bootstrap

## SYS nodes

Run the matching SRVR from the GitHub build. The existing SRVR firmware authority coordinates CTRL, W1P and CTRL-TS in that order. The PDM's update runs separately.

For a USB recovery flash, use the matching GitHub artifact's FIRMWARE/STAGED_SOURCE folders and the board settings in [ARDUINO_IDE_SETTINGS_v26.11.09.04.md](ARDUINO_IDE_SETTINGS_v26.11.09.04.md). The staged CTRL sketch has the exact compiled CTRL-TS image embedded. The CTRL source in the repository carries a build guard until that image is staged.

A CTRL-TS that has already migrated to the safe updater (safe_ota=2) can use the usual managed update. For a much older CTRL-TS, follow the matching safe-updater recovery procedure before relying on self-update.

## Optional Olimex PDM

A standalone PDM needs one USB upload to install its integrated firmware and dual-slot OTA partition table. Follow [the PDM bootstrap and recovery guide](PDM_BOOTSTRAP_v26.11.09.04.md).
