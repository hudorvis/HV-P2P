# HV P2P v26.10.06.10 deep code audit

Date: 2026-10-06
Baseline: `v26.10.06.09`

## Scope lock

The observed failure is isolated to SRVR -> CTRL presentation telemetry. Joystick/motion control remained live, automatic update had completed, and SRVR could still receive CTRL/CTRL-TS diagnostics. Therefore no motion, watchdog, calibration, W1P, Leadshine or updater state machine is modified.

After normalising release identity, the production source diff versus `.06.09` is limited to `SRVR_GitHub.../backend.py`.

## Evidence from the symptom

CTRL's fallback HMI packet deliberately contains:

- `System / Active` -> rendered as `System | Active`;
- neutral `AUX 1` through `AUX 5` labels;
- zero position/speed values;
- no preset names/positions.

Those values match the reported touchscreen exactly. Meanwhile CTRL joystick packets continued reaching SRVR, proving the opposite-direction control path was alive.

## Transport asymmetry

Before `.06.10`:

- CTRL -> SRVR heartbeat/control arrived at SRVR's controller worker bound to UDP/5000;
- heartbeat ACK and the redundant firmware-discovery reply used that proven bound path;
- SRVR -> CTRL `DSP1` display data used a separate unbound UDP socket.

The updater had already needed a redundant bound-path firmware reply to remove dependence on a one-way beacon. The display path still retained that same unbound-source weakness.

## `.06.10` correction

SRVR now stages only the latest display snapshot under a small lock. The controller worker drains that staged snapshot and calls `sendto()` on its own bound UDP/5000 socket. The worker receive timeout is 25 ms so display handoff latency is bounded while heartbeat responses remain immediate. If a display send fails, the latest snapshot is restored for retry unless a newer one has already replaced it.

This keeps one owner for the bound socket, coalesces stale display frames automatically, and makes DSP1 use the exact same source address/port path already proven by heartbeat/control traffic.

CTRL's fallback packet, CTRL/CTRL-TS RS485 protocol, HMI compatibility gate, firmware updater, W1P watchdog and all operator-state semantics are unchanged.

## Verification

- `HMI_DISPLAY_BOUND_TRANSPORT_0610_PASS`.
- 370 EdgeBox integration checks PASS.
- Historical updater/RS485/safe-update/calibration/motion regressions PASS.
- 53 build-pipeline checks PASS.
- Modbus/wire/speed/motion contracts PASS.
- Release consistency, source hygiene, Python syntax and SRVR preflight PASS.
- PySide runtime remains a GitHub CI gate because PySide6 is unavailable locally.
