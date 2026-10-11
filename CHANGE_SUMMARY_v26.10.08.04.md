# HV P2P v26.10.08.04 change summary

Date: 2026-10-08

Source baseline: **v26.10.08.03**. The approved AI0/5 V W1P E-stop, EdgeBox DO0 brake control, CTRL-TS marker smoothing, updater, motion, calibration, AUX, limits and all unrelated behaviour remain locked.

## Change 1 — restore established W1P ↔ EL7 communication format

The `.08.02/.08.03` factory-default experiment is reversed. W1P normal operation is restored to the original HV P2P Leadshine settings:

- **115200 baud**
- **8N1**
- **Modbus slave ID 1**
- EL7 `P05.29 = 4`
- EL7 `P05.30 = 6`
- EL7 `P05.31 = 1`

The alternate EL7 factory format **38400 / 8N2** remains available only as a stopped/read-only commissioning diagnostic probe. It never promotes motion authority or changes the operational UART configuration.

## Change 2 — make Leadshine/RS485 faults visible in the SRVR log

W1P already reported the relevant state in STATUS and printed detailed diagnostics to its local USB serial console, but SRVR only converted that state into a generic Connected/Disconnected display. `.08.04` adds transition-only SRVR log entries for:

- no valid Modbus reply at 115200/8N1;
- detection of the EL7 at the alternate 38400/8N2 factory format, including the exact P05 settings required;
- physical link alive but required configuration-register reads failing;
- physical link alive but EL7 parameter values mismatching the HV P2P contract;
- valid link/configuration but unsafe/unavailable motor feedback/SRDY;
- recovery to a fully verified connected state.

The diagnostic logger is keyed to state changes, so the 20 Hz W1P STATUS stream does not flood the operator log or saved log file.

## Preserved v26.10.08.03 behaviour

- W1P local E-stop remains **AI0 / 5 V**, fail-closed, with the existing healthy window and debounce.
- EdgeBox **DO0 / GPIO40** remains the physical 24 V holding-brake switch; LOW/off applies the brake and EL7 logical `BRK-OFF` remains the sequencing authority.
- CTRL → W1P → CTRL-TS firmware ordering and CTRL-TS progress display remain unchanged.
- Motion, limits, calibration, AUX, watchdogs, firmware authority and approved UI layout remain unchanged.

## Validation

- `test_leadshine_commissioning_contract.py` now locks the restored 115200/8N1/ID1 operational format and stopped 38400/8N2 diagnostic probe.
- `test_w1p_rs485_fault_logging_100804.py` locks the SRVR transition-based RS485 fault/recovery logging contract.
- Existing AI0 E-stop, DO0 brake, updater, motion, calibration, AUX and historical regression tests remain enabled.
