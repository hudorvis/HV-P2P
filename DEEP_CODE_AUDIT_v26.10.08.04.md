# HV P2P v26.10.08.04 deep code audit

Date: 2026-10-08
Baseline: `v26.10.08.03`

## Scope lock

Functional changes are restricted to the W1P ↔ EL7 Modbus framing restoration and SRVR Leadshine/RS485 diagnostic logging. CTRL, CTRL-TS, QML layout, motion shaping, calibration, AUX, limit logic, firmware authority/update ordering, W1P AI0 E-stop logic and DO0 brake sequencing remain locked apart from release identity and test/document references.

## Leadshine Modbus restoration

W1P normal UART1 operation is restored to the original project contract:

- `RS485_BAUD = 115200`
- `SERIAL_8N1`
- slave ID `1`
- expected `P05.29 = 4` (8N1)
- expected `P05.30 = 6` (115200)
- expected `P05.31 = 1`

The existing Modbus CRC, inter-frame gap, reply timeout, retry count, link debounce and stale-reply watchdog are unchanged. The safe commissioning probe is inverted back to its original purpose: only while motion writes are disabled, Servo Enable is inhibited, service operation is inactive and all velocity states are zero, W1P temporarily probes **38400/8N2** read-only, restores 115200/8N1 immediately, and restores all normal link-health counters. The probe cannot establish operational authority.

## SRVR RS485 diagnostics

The SRVR now interprets existing W1P STATUS evidence into user-visible log transitions. It distinguishes:

1. no valid operational Modbus response;
2. alternate factory-format detection;
3. configuration-register read fault;
4. parameter mismatch with exact reported values where available;
5. feedback/SRDY fault after link/configuration validation;
6. full recovery/verification.

The logger stores a diagnostic signature and only emits when that signature changes. It therefore adds useful fault history to the normal/saved SRVR log without periodic 20 Hz spam.

## Preserved safety paths

- W1P AI0 local E-stop remains fail-closed and unchanged from `.08.03`.
- EdgeBox DO0 brake output remains fail-applied LOW and still requires verified EL7 logical brake sequencing.
- Loss of RS485 authority continues to inhibit drive writes and brake release through the existing safety gates.
- Safe OTA/service/reboot/reset requirements remain unchanged.
- CTRL → W1P → CTRL-TS updater ordering and status reporting remain unchanged.

## Regression locks

- Updated `test_leadshine_commissioning_contract.py` locks 115200/8N1/ID1 and the stopped diagnostic probe.
- Added `test_w1p_rs485_fault_logging_100804.py` to lock operator-visible RS485 fault/recovery messages and transition-only behavior.
- Existing `.08.03` AI0 E-stop and `.08.02` DO0 brake tests remain active.
- Historical CTRL/CTRL-TS/SRVR/motion/calibration/AUX/updater regressions remain in `run_all_source_checks.py`.
