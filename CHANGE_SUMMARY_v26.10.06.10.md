# HV P2P v26.10.06.10 change summary

Date: 2026-10-06

Locked baseline: `v26.10.06.09`.

This revision changes only the SRVR -> CTRL display-data transport plus the directly related regression tests/release identity. Motion, safety, calibration, AUX, W1P/Leadshine, CTRL-TS rendering, firmware authority and automatic-update behavior remain locked.

## Bench symptom

After a successful automatic update, SRVR still received CTRL joystick/control traffic and could see CTRL/CTRL-TS, but CTRL-TS showed its local/fallback operator data: `System | Active`, `Aux 1..5`, no presets, zero/no live position/speed data. SRVR itself correctly showed `System | Uncalibrated`.

That combination proves the CTRL -> SRVR control path and CTRL <-> CTRL-TS RS485 link can be healthy while the independent SRVR -> CTRL `DSP1` display stream is absent. CTRL's `buildFallbackDisplayPacket()` contains exactly the values seen on the panel.

## Root transport weakness corrected

The controller receive worker owns a socket bound to UDP/5000 and that path is already proven by CTRL heartbeat/control traffic and heartbeat ACKs. `DSP1`, however, was still transmitted from a separate unbound UDP socket. On a multi-interface/source-route edge case, CTRL can therefore accept the bound heartbeat path while rejecting/never seeing the one-way display datagram, leaving CTRL-TS on fallback data.

`.06.10` coalesces the latest `DSP1` snapshot and has the controller worker transmit it from the same bound UDP/5000 socket used by the proven heartbeat return path. The worker services the staged display snapshot at up to 40 Hz; SRVR still builds `DSP1` at the existing bounded cadence and CTRL still derives/forwards the same HMI1/HMS1/HMG1/HMM1 payloads.

No display content, status priority, motion command or safety decision is changed.

## Regression hardening

- Added `tools/test_hmi_display_bound_transport_0610.py`.
- Updated the PySide `test_backend_logic` transport fixture to stage and flush the real bound-socket path rather than asserting a call to the obsolete direct/unbound display socket.
- The new contract requires DSP1 to be staged, the controller worker to own/flush it through its bound UDP/5000 socket, failed sends to retain the latest snapshot for retry, and the existing neutral CTRL fallback semantics to remain unchanged.

## Verification

The complete source/static suite passes through all functional checks: 370 EdgeBox integration checks, historical updater/RS485/calibration/motion regressions, `.06.10` bound-display regression, 53 build-pipeline checks, Modbus/wire/speed/motion contracts, release consistency, source hygiene, Python syntax and SRVR preflight.

PySide6 is unavailable in the local source-audit environment, so the exact desktop runtime `tools.test_backend_logic` remains a GitHub CI gate. Native ESP32/frozen desktop builds remain GitHub Actions gates.
