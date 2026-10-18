# HV P2P v26.10.19.01 initial / recovery bootstrap

## Normal update from v26.10.08.04

If the installed system is already on `v26.10.08.04`, no special ESP32 bootstrap is required. Build `.08.05` in GitHub Actions, install/run the `.08.05` SRVR application, and allow the existing firmware-authority sequence to converge CTRL -> W1P -> CTRL-TS.

The `.08.05` functional fix is SRVR-only; CTRL, W1P and CTRL-TS production behavior is unchanged apart from release identity. Their normal automatic update path remains available so the complete system can converge to one release version.

## macOS crash-recovery note

If the `.08.04` macOS SRVR crashes immediately after opening, it may not remain alive long enough to coordinate device updates. Install the `.08.05` SRVR app first. The `.08.05` frozen-app CI gate executes the exact RS485-diagnostic -> DSP1-build sequence that crashed `.08.04` before publishing the macOS artifacts.

## Older CTRL-TS safe-updater bootstrap

Systems already migrated through the `safe_ota=2` CTRL-TS bootstrap require no additional manual touchscreen bootstrap for `.08.05`. If recovering a much older touchscreen that predates the safe updater, use the matching release's recovery procedure before relying on automatic CTRL-TS self-update.
