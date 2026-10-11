# HV P2P v26.10.08.05 deep code audit

Date: 2026-10-11
Baseline: `v26.10.08.04`

## Crash evidence

The `.08.04` macOS Intel crash is a native `EXC_BAD_ACCESS` on the Qt main thread. The reported stack enters `_tick`, then `_send_controller_display_packet`, then `_build_controller_display_packet`, and finally fails inside Nuitka's generated `CALL_FUNCTION_WITH_POS_ARGS1` helper. It is not a Python exception, RS485 socket failure, QML load failure or macOS permission rejection.

A source diff against `.08.03` confirms `_build_controller_display_packet()` is unchanged byte-for-byte. The new `.08.04` RS485 diagnostics execute immediately before the normal motion/display phase in `_tick`, making that new path the only functional SRVR delta in the failing sequence.

## Minimal hardening

Functional changes are restricted to the `.08.04` SRVR diagnostic implementation and release identity:

- diagnostic booleans are encoded with literal `"1"`/`"0"` expressions rather than direct special-method calls;
- `_log_w1p_rs485_diagnostics()` now reduces fields and queues only the newest transition message;
- `_tick` flushes that pending message only after `_send_controller_display_packet()` has completed;
- diagnostic wording, transition signatures, saved-log routing and operator information remain equivalent.

No DSP1 field, HMI rate, marker rate, motion calculation, safety authority, firmware coordinator or QML layout was changed.

## Frozen runtime gate

The existing packaged-app smoke test previously shut the backend down before a realistic timer/RS485 diagnostic sequence could exercise this path. `.08.05` adds an explicit compiled-path fixture in `main.py` that performs diagnostic reduction followed by twenty DSP1 builds before the deferred log is emitted. Both macOS architecture jobs execute this inside the completed signed app and again from the extracted release ZIP.

## Preserved safety/communications

- EL7 operational format remains 115200/8N1/ID1 with factory 38400/8N2 read-only diagnostic probing.
- W1P AI0 local E-stop remains fail-closed.
- EdgeBox DO0 brake output remains fail-applied LOW and still follows verified EL7 logical brake sequencing.
- Loss of RS485 authority continues to inhibit drive writes and brake release through existing gates.
- CTRL -> W1P -> CTRL-TS updater ordering and progress reporting remain unchanged.
