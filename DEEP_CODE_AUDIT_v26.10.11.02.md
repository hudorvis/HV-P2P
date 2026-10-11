# HV P2P v26.10.11.02 deep code audit

Date: 2026-10-11  
Baseline: `v26.10.11.01`

## 1. GitHub evidence and root cause

The supplied macOS Intel job successfully imported `backend.py` and then failed in `tools/test_backend_logic.py` during the config recovery regression. The failing access was to a temporary `hvp2p-srvr-smoke-*` config path that no longer existed/contained the expected config.

The `.11.01` smoke hardening had made `_config_file_path()` allocate a **new temporary data directory for every Backend instance** and delete it from each instance's `shutdown()`. That is too narrow for a restart/recovery regression: two Backend objects created inside one test process are intended to represent two launches of the same application data store.

## 2. Persistence fix

`backend.py` now owns one process-scoped `_SMOKE_DATA_DIR` guarded by a lock. `_process_smoke_data_dir()` lazily creates it and registers process-exit cleanup with `atexit`.

This preserves all required properties simultaneously:

- smoke tests never use the real operator config path;
- independent CI source/frozen processes never share smoke state;
- multiple Backend instances inside one process share the same private config/backup, matching production restart semantics;
- shutting down one temporary Backend cannot delete persistence still required by another object/test step.

`test_backend_logic.py` now explicitly asserts `b2._config_path == b._config_path` before validating previous-good `.bak` recovery.

## 3. Desktop/frozen runtime hardening retained

The `.11.01` native-runtime work remains unchanged:

- Python 3.12.10 is pinned in desktop CI;
- PySide6 6.11.1 and Nuitka 4.2.2 are pinned;
- CI verifies Nuitka is not silently replaced by `pyside6-deploy`;
- frozen macOS smoke tests retain phase markers, `faulthandler`, 200 DSP1 builds and Apple crash-report capture;
- nested functions/lambdas remain absent from `backend.py` hot paths.

The new fix does not reintroduce the `.08.04/.08.05` native call pattern.

## 4. Firmware/control lock verification

Compared with `.11.01`, after normalising release identity:

- W1P firmware: unchanged;
- CTRL firmware: unchanged;
- CTRL-TS firmware: unchanged;
- all SRVR QML files: unchanged.

Therefore the following approved behaviour remains locked: 115200/8N1/ID1 EL7 operation, read-only 38400/8N2 diagnostic probe, AI0/5 V W1P E-stop, DO0 physical brake switching under verified EL7 logical BRK-OFF authority, watchdogs, predictive limits, motion profiles, calibration, AUX, Free-D, marker smoothing and CTRL -> W1P -> CTRL-TS update ordering.

## 5. Validation results

Post-fix source validation:

- EdgeBox integration: **386 checks PASS**;
- build pipeline: **58 checks PASS**;
- audit/history bench regressions through native-build orchestration: PASS;
- Modbus CRC host test: PASS;
- SRVR wire contract: PASS;
- Speed Mode contract: PASS;
- motion innovations contract: PASS;
- release consistency: PASS;
- source hygiene: PASS after removing local generated `__pycache__` test artifacts;
- Python syntax: PASS, **71 files**;
- SRVR preflight: PASS;
- backend runtime regression: PASS using a QtCore-compatible local test double, including the exact config backup/recovery case that failed GitHub.

The combined source runner exceeded this environment's execution limit after native-build orchestration; remaining tests were completed separately rather than being assumed to pass.

## 6. Remaining external gates

This environment cannot execute the real PySide6/Nuitka macOS app or compile the ESP32 targets. GitHub Actions remains authoritative for:

- native ESP32 firmware compilation;
- macOS Intel frozen source/frozen-app smoke;
- macOS Apple Silicon frozen smoke;
- Windows x64 frozen smoke;
- final matched release packaging.

Physical EL7 RS485, brake-current/thermal margin, E-stop voltage-input hardware and real OTA/motion remain bench commissioning gates.
