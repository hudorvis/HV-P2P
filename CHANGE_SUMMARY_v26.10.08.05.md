# HV P2P v26.10.08.05 change summary

Date: 2026-10-11

Source baseline: **v26.10.08.04**. The approved 115200/8N1 W1P↔EL7 link, AI0/5 V W1P E-stop, EdgeBox DO0 brake control, CTRL-TS marker smoothing, updater, motion, calibration, AUX, limits and all unrelated behaviour remain locked.

## Change 1 — fix macOS Intel SRVR startup crash introduced in .08.04

The user-supplied macOS crash report shows the frozen `.08.04` app launching normally and then failing on the Qt main timer with `EXC_BAD_ACCESS (SIGSEGV)`. The native stack is `_tick -> _send_controller_display_packet -> _build_controller_display_packet -> Nuitka CALL_FUNCTION_WITH_POS_ARGS1`.

The DSP1 builder itself is source-identical to `.08.03`; the only new `.08.04` path immediately ahead of it was the Leadshine/RS485 diagnostic reducer/log emitter. `.08.05` therefore hardens only that new path:

- removes direct `bool.__str__()` special-method calls from the frozen diagnostic signature path;
- makes the diagnostic reducer plain-data only and queues one transition message;
- defers the Qt `logChanged` emission until after DSP1/marker/motion work for the current 25 ms tick is complete;
- preserves the same transition-only no-response, factory-format, configuration, feedback and recovery messages.

This avoids the new re-entrant compiled Python/PySide call sequence without changing the controller display packet contents, rate or authority.

## Change 2 — add a frozen-runtime regression gate for this exact crash path

The normal source tests could not catch a native Nuitka/PySide crash. The packaged SRVR smoke test now explicitly executes:

1. W1P RS485 diagnostic reduction using a disconnected EL7 fixture;
2. twenty consecutive `_build_controller_display_packet()` calls;
3. deferred diagnostic log emission and Qt event processing.

That exact sequence runs inside the **frozen macOS Intel and Apple Silicon app** during GitHub Actions, after packaging/signing and again after ZIP round-trip extraction. A release cannot publish if the native crash recurs there.

## Preserved v26.10.08.04 behaviour

- W1P operational EL7 Modbus remains **115200 baud / 8N1 / slave ID 1** (`P05.29=4`, `P05.30=6`, `P05.31=1`).
- 38400/8N2 remains stopped/read-only diagnostic only.
- W1P local E-stop remains **AI0 / 5 V**, fail-closed.
- EdgeBox **DO0 / GPIO40** remains the physical 24 V holding-brake switch; LOW/off applies the brake and EL7 logical `BRK-OFF` remains sequencing authority.
- CTRL -> W1P -> CTRL-TS firmware ordering/status remains unchanged.
- Motion, limits, calibration, AUX, watchdogs, firmware authority and approved UI layout remain unchanged.

## Validation

- Added `test_macos_frozen_rs485_diag_crash_100805.py`.
- Updated the `.08.04` RS485 fault-logging regression for queued/deferred emission while preserving message semantics.
- Existing AI0 E-stop, DO0 brake, updater, motion, calibration, AUX and historical regression tests remain enabled.
- Native Arduino and frozen PySide/Nuitka compilation remain GitHub Actions gates.
