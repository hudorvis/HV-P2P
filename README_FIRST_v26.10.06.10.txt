HV P2P v26.10.06.10 - GitHub Ready Source

Locked baseline: v26.10.06.09.

This revision fixes the SRVR -> CTRL display-data path only. The bench symptom (live joystick/control on SRVR while CTRL-TS showed System | Active, Aux 1..5 and no live telemetry) exactly matches CTRL's neutral fallback HMI packet.

DSP1 display packets are now staged and transmitted by SRVR's proven controller worker bound to UDP/5000, the same path already used for CTRL heartbeat/control return traffic. The separate unbound display source is no longer used for DSP1.

Motion, safety, calibration, AUX semantics, W1P/Leadshine, CTRL-TS rendering and automatic firmware-update behavior remain locked to v26.10.06.09 apart from release identity.

GitHub Actions/native compilation and PySide runtime remain authoritative. No firmware binaries are included in this source package.
