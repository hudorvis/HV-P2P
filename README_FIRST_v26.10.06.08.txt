HV P2P v26.10.06.08 - GitHub Ready Source

Locked baseline: v26.10.06.07.

This revision is restricted to the current three requested items:
- CTRL-TS travel marker uses verified sample-to-sample interpolation instead of forward prediction, eliminating high-speed overshoot/back-correction while keeping numeric position/control authoritative;
- System | Ramping remains yellow whenever the skate is physically inside either configured end ramp zone, including when stopped; Near/Far Limit retain priority inside 1.0 m;
- W1P Encoder / Leadshine EL7-RS RS485 path was audited end-to-end; no W1P production behavior change was required.

Automatic firmware updating, calibration/AUX behavior, limits, W1P 500 ms watchdog, ~150 ms SRVR VEL refresh, Leadshine control architecture and approved Run/Settings UI remain locked from v26.10.06.07.

GitHub Actions/native compilation remains authoritative. No firmware binaries are included in this source package.
