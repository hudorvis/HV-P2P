HV P2P v26.10.06.11 - GitHub Ready Source

Locked baseline: v26.10.06.10.

This revision changes only CTRL-TS cable-progress display smoothness.

A dedicated change-driven 20 Hz maximum marker-only path now carries SRVR's canonical verified position fraction to CTRL-TS without increasing the full DSP1/HMI1/HMM1 refresh rates. CTRL-TS still renders locally at approximately 50 Hz and never predicts beyond the newest real sample.

Hardware Encoder position remains genuinely source-limited to the existing 10 Hz Leadshine feedback poll; that W1P control/feedback timing is intentionally unchanged. Virtual position can supply 20 Hz marker samples because SRVR state is updated at 40 Hz.

RS485 POLL/EVENT priority, firmware-exclusive bus ownership, motion, safety/watchdogs, calibration, AUX behavior, updater, UI layout and all other approved v26.10.06.10 behavior remain locked.

GitHub Actions/native compilation and PySide runtime remain authoritative. No firmware binaries are included in this source package.
