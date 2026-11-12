# HV P2P SYS v26.11.12.05

- Current HV P2P control and status use UDP 5760. Firmware authority, EdgeBox service pages and PDM/WSI dashboards and APIs use TCP 5760.
- SRVR starts when TCP 5000 or 5088 is occupied. These ports serve legacy OTA when available. SRVR accepts legacy W1P observations for upgrade coordination and uses current-port replies for motion and position.
- The PDM dashboard transitions to `http://172.20.1.110:5760/` at its default IP. The SRVR monitor can reach the old dashboard during the upgrade.
- Free-D port values remain configurable for the external Free-D equipment. CTRL-TS communicates with CTRL over RS485.
