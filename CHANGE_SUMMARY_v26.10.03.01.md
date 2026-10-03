# HV P2P v26.10.03.01 change summary

This revision starts directly from the approved `v26.10.02.05` GitHub-ready source and addresses the CTRL ↔ CTRL-TS half-duplex RS485 instability without changing the approved UI or W1P/Leadshine motion architecture.

## CTRL ↔ CTRL-TS reliability

- Enforced exactly one normal RS485 transaction at a time.
- Prevented a second POLL while the previous POLL/EVENT response is outstanding.
- Prevented display/config/HELLO traffic from pre-empting an outstanding POLL.
- Added a 35 ms POLL response timeout and diagnostics.
- Reduced full HMI display forwarding to a maximum of 4 Hz (250 ms minimum interval) while retaining changed-packet suppression and keepalive.
- Made AUX/event delivery acknowledgement-based and retry-safe with event IDs and duplicate suppression.
- Replaced the CTRL-TS dynamic `String` event queue and AUX command construction with fixed buffers.
- Added CRC/resync, poll, EVENT, display TX and queue-drop counters and SRVR fault-counter logging.
- Preserved the safe headless CTRL-TS firmware updater and exclusive firmware-transfer ownership of RS485.
- Preserved CTRL-TS boot ID/reset reason reporting.

## Regression coverage

Added `tools/test_hmi_bus_serialization_contract.py` to reproduce the .02.05 stale/lost AUX failure and verify serialization, timeout, retry and duplicate handling.

## Safety architecture deliberately unchanged

- W1P independent 500 ms VEL freshness watchdog.
- SRVR ~150 ms non-zero VEL refresh.
- AI0 E-stop and AI1 joystick mapping.
- Existing E-stop/hard-limit protections.
- Predictive stopping/dynamic soft limits.
- Leadshine velocity-control architecture.
- Approved CTRL-TS/SRVR UI design and calibration wording.

GitHub Actions/native compilation remains authoritative for firmware binaries.
