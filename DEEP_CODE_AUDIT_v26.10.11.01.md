# HV P2P v26.10.11.01 deep code audit

Date: 2026-10-11  
Baseline: `v26.10.08.05`

## 1. Evidence reviewed

The supplied GitHub log shows the macOS Intel app successfully compiled, had its bundle metadata/icon applied, passed `codesign --verify`, and then crashed only when the frozen executable itself ran `--smoke-test`. The shell reported `Segmentation fault: 11` / exit 139.

The build log also records `pyside6-deploy` installing Nuitka 4.3 dynamically. That made the desktop compiler an uncontrolled build input.

The earlier `.08.04` Apple crash report independently showed a native `EXC_BAD_ACCESS (SIGSEGV)` on the Qt main thread through `_tick -> _send_controller_display_packet -> _build_controller_display_packet -> Nuitka CALL_FUNCTION_WITH_POS_ARGS1`.

## 2. Desktop build-chain audit

### Corrected

- Python is pinned to `3.12.10` in firmware/macOS/Windows GitHub jobs.
- `requirements.txt` pins `PySide6==6.11.1` and `Nuitka==4.2.2`.
- `pysidedeploy.spec` is patched to retain `nuitka==4.2.2`.
- CI checks Nuitka identity before/after pyside6-deploy stages, preventing silent compiler replacement.
- macOS frozen-smoke failures now print phase output and recent Apple crash reports, both before packaging and again after ZIP extraction.
- Smoke-test config writes use a per-process temporary directory and are removed at shutdown; CI smoke stages cannot contaminate each other or touch a real operator config.

### Intentionally unchanged

- PySide6 remains 6.11.1; changing the Qt binding/runtime in the same repair would introduce a much larger UI/runtime variable.
- Deployment remains through `pyside6-deploy`; changing packagers would be a redesign outside this issue.
- QML duplicate-inclusion messages from Nuitka are warnings, not the failing step, so no QML packaging refactor was made.

## 3. SRVR native-call audit

All nested function/lambda creation inside `backend.py` has been removed. This includes hot telemetry/property paths and startup migration helpers. The DSP1 builder no longer calls local closure formatters.

The replacements preserve the same values and data structures:
- telemetry counters still clamp to non-negative integers;
- migrated config defaults and ramp conversions are unchanged;
- geometry remains sorted by X;
- calibration summaries expose the same keys/text;
- DSP1 wire fields and formatting remain unchanged.

No change was made to transport cadence, authority state, Free-D calculation, motion ramps, predictive limits, joystick mapping or firmware coordination.

## 4. Firmware/safety audit

The firmware source remains functionally locked to `.08.05` except release identity.

Verified contracts retained:
- W1P EL7 operational UART 115200/8N1/ID1;
- alternate 38400/8N2 probe is read-only/stopped diagnostic only;
- W1P AI0 local E-stop starts fail-closed and cannot clear on ADC/I2C fault;
- DO0 boot/default is brake-applied/off and release requires verified EL7 brake authority;
- loss of RS485/feedback prevents new brake release/drive writes;
- W1P 500 ms VEL watchdog and normal 100 ms Leadshine position feedback remain unchanged;
- CTRL/CTRL-TS half-duplex update/event ordering remains serialized;
- updater authority/order remains CTRL → W1P → CTRL-TS;
- `.06.11` DMP1/HMP1 real-position marker path remains unchanged.

## 5. Build/release audit

The source suite includes architecture/partition guards, staged HMI embedding, immutable firmware authority hashes, release identity checks, source hygiene checks, Modbus frame tests and desktop source/frozen smoke gates.

The frozen smoke now stresses the exact diagnostic→DSP1 path 200 times and records `SMOKE PHASE` progress. The build validator now has **58** explicit pipeline checks. Local source validation passed **386** EdgeBox integration checks plus every constituent regression; the combined runner timed out near its final motion checks, which were then run separately and passed. A frozen failure remains a hard CI failure; this revision does not claim a macOS native pass until GitHub executes it.

## 6. Residual commissioning gates

These require real hardware and cannot be proven by source tests:
- EL7 parameter values and RS485 physical wiring/termination;
- actual brake-coil current/thermal margin on EdgeBox DO0;
- AI0 voltage-input hardware configuration;
- physical E-stop and brake timing;
- real CTRL/W1P/CTRL-TS OTA over the installed network.

Those remain explicit items in the native/bench checklist.
