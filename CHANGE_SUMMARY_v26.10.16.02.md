# HV P2P v26.10.16.02 — SRVR startup and transition logging

Release date: **16 October 2026**. Approved source baseline: **v26.10.16.01**.

## Changes (SRVR logging and validation only)

- On SRVR startup, Log records release identity, configured CTRL/W1P endpoints and starts a **3-second discovery window** so normal boot ordering does not create misleading immediate faults.
- On completion of discovery, SRVR records an initial **state for every connection**, including unavailable ones: CTRL UDP, W1P UDP/validated STATUS, EL7 Modbus/RS485, CTRL-TS HMI, CTRL analogue joystick input, CTRL/W1P firmware agreement and Free-D input.
- Link state is derived from **existing accepted, freshness-gated telemetry**. Valid EL7 Modbus data is treated as RS485 Active regardless of Servo Ready/configuration; those remain separate strict motion/safety gates.
- Each change to Active/Fault/Offline/Unverified/Matched/Mismatch is logged once. Startup entries are batched into one Qt Log notification. Loss/degradation is debounced for 0.75 s; healthy recovery is immediate. No 25 ms log spam or periodic redraw churn.
- CTRL-TS is explicitly labelled **optional**, Free-D is labelled optional/disabled as appropriate; absence of either does not become a new motion inhibition.
- Connection-log emission happens on the Qt timer **after** DSP1 construction, preserving the frozen macOS native-crash mitigation. Frozen executable smoke test now exercises this path.
- Added `tools/test_srvr_startup_connection_logging_101602.py` to source-check orchestration. It dynamically exercises the two exact backend methods and proves cold-start, recovery, missing HMI, firmware mismatch, link transient suppression, and full EL7 recovery without touching motion logic.

## Locked behavior

All CTRL, CTRL-TS and W1P production code is **identical to v26.10.16.01 except for release-version identity**. Existing Free-D geometry/QML UI, DSP1/DMP1, CTRL/AUX, firmware authority/order, Leadshine 115200 8N1/ID 1, EL7 Servo Ready/motion safety, W1P AI0 5 V E-stop, DO0 brake and watchdogs are unchanged. SRVR strict `winch_rs_status` still inhibits motion when appropriate.

## Limitations and verification

The source audit and contract tests do not substitute for **GitHub Actions native Arduino compilation, PySide6 backend runtime tests, frozen Intel/Apple Silicon/Windows smoke tests or powered bench checks**. See `DEEP_CODE_AUDIT` and `NATIVE_BUILD_AND_BENCH_CHECKLIST` for results and procedures. Do not claim native builds pass until CI completes.
