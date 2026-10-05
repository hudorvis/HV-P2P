# HV P2P v26.10.06.01 deep code audit

Date: 2026-10-06

## Scope

This audit began from the complete `v26.10.05.11` GitHub-ready source and the failing GitHub Actions log. The earlier authoritative project lineage remains the user-supplied `v26.10.05.06` source. The scan covered:

- the exact macOS PySide backend test failure;
- production `W1PClient` firmware snapshot interface and final CTRL-TS update-order gate;
- all Fake/Mock W1P/CTRL objects in the SRVR regression tree;
- every call to `firmware_snapshot()` and the `.05.11` background firmware coordinator methods;
- GitHub workflow paths/version metadata for macOS Intel, macOS Apple Silicon and Windows x64;
- source/protocol regression ordering;
- native firmware build/orchestration contracts;
- release consistency, source hygiene and Python syntax.

## Finding A — exact GitHub failure

The failing job proved that `backend.py` itself imported correctly. The exception occurred later inside `tools.test_backend_logic` after the test replaced `b.w1p` with a local `FakeW1P`.

Production `.05.11` introduced:

- `W1PClient._update_firmware_snapshot(...)`; and
- `W1PClient.firmware_snapshot()`.

`HVP2PBackend._ctrl_ts_update_allowed()` intentionally calls `self.w1p.firmware_snapshot()` so final-stage firmware ordering does not depend on Qt draining the W1P receive queue.

The test double still exposed only the older methods (`send`, velocity-refresh helpers, `reconfigure`, `close`) and `connected`. Therefore the first display-packet build that evaluated `fw_ts_allowed` failed with an AttributeError.

This was a **test-double interface regression**, not a firmware updater/runtime failure.

## Finding B — no second FakeW1P implementation exists

A complete scan of `SRVR_GitHub.../tools` found one `FakeW1P` class only. There is no second mock that would fail later for the same missing interface.

All source references to `firmware_snapshot()` are confined to:

1. the real `W1PClient` implementation;
2. `_ctrl_ts_update_allowed()`; and
3. the updater-convergence regression contracts.

The corrected test double now mirrors the production snapshot shape and advertises a fresh matched current release for the unrelated DSP/AUX transport test block.

## Finding C — source-only CI had a coverage gap

`run_all_source_checks.py` runs without PySide6 in the source-audit/firmware job. The real `test_backend_logic.py` is intentionally deferred until desktop dependencies are installed. That is why `.05.11` could pass every source/static test and still fail later in the macOS runtime job.

### Fix

`test_backend_test_double_contract_0601.py` is now part of the source suite. It uses Python AST parsing to locate `FakeW1P` and requires the production firmware-order interface (`firmware_snapshot`) whenever backend code calls it. It also requires the fake to carry a deliberate matched/current snapshot rather than a meaningless stub.

This moves detection of future production/test-double interface drift to the earliest CI job.

## Finding D — production firmware-update state machine should not be changed for this error

A second pass confirmed that the reported stack trace does not indicate an updater state-machine failure. It occurs after backend construction, in a regression-only replacement object.

Accordingly `v26.10.06.01` does **not** add another runtime firmware-coordinator workaround. The `.05.11` production behavior remains intact:

- background release discovery independent of Qt focus/timer scheduling;
- background W1P firmware snapshot/order state;
- CTRL -> W1P -> CTRL-TS ordering;
- W1P discovery grace and bounded absence escape;
- new-SRVR-session exact manifest/SHA re-verification;
- fail-safe shutdown ordering;
- CTRL-TS REBOOT ACK treated only as command receipt;
- post-reboot exact identity/reboot proof;
- autonomous verified-image fallback reboot;
- legacy safe-updater convergence.

## Safety invariants rechecked

The version-bumped sources pass the same 370 EdgeBox source-level integration checks. The following contracts remain unchanged:

- W1P `W1P_VEL_COMMAND_TIMEOUT_MS = 500`;
- SRVR normal non-zero VEL keepalive approximately 150 ms;
- AI0 E-stop / AI1 joystick mapping;
- joystick-neutral re-arm after genuine safety interruption;
- hard limits and predictive/dynamic soft limits;
- Leadshine velocity architecture and Modbus commissioning guards;
- CTRL <-> CTRL-TS half-duplex single-flight RS485 with EVENT ACK/retry;
- transactional calibration commit/cancel semantics.

## Version/release audit

Because this correction is issued on 6 October 2026, the release sequence resets to `v26.10.06.01`.

GitHub metadata was updated consistently:

- APP_VERSION: `26.10.06.01`;
- macOS CFBundleShortVersionString source: `26.10.6`;
- macOS CFBundleVersion source: `2610.6.1`;
- firmware/sketch/SRVR directory and artifact names use `v26.10.06.01`.

## Verification result

All source/static checks available in this environment pass. The combined source runner reached the environment execution limit after build-pipeline validation; the remaining checks were rerun individually and all passed.

PySide6 is not installed locally, so the exact runtime test that failed in GitHub cannot truthfully be claimed as locally executed. Its missing interface is now corrected directly and additionally protected by the source-level AST contract. GitHub Actions remains authoritative for PySide runtime, frozen desktop builds and ESP32 native compilation.
