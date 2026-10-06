HV P2P v26.10.06.07 - GitHub Ready Source

Locked baseline: v26.10.06.06.

This revision is restricted to automatic firmware-release recovery and CTRL-TS splash/connection stability:
- redundant SRVR_FW release discovery on the proven CTRL heartbeat return path;
- CTRL-local CTRL-TS fallback no longer depends on an optional SRVR session token after exact authority verification;
- lost final CTRL progress status self-heals after CTRL reboot/HELLO;
- CTRL-TS no longer flashes Home while SRVR is offline because firmware-screen release and stale HMI status are connection-aware.

Motion, calibration, limits, W1P watchdog, Leadshine control and approved UI behavior remain locked.

GitHub Actions/native compilation remains authoritative. No firmware binaries are included in this source package.
