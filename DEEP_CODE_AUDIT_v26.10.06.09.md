# HV P2P v26.10.06.09 deep code audit

Date: 2026-10-06
Baseline: `v26.10.06.08`

## Scope lock

No production behavior change is permitted in this revision. A normalized `.06.08 -> .06.09` production diff reports zero functional changes across CTRL, W1P, CTRL-TS, SRVR backend, QML, firmware authority and workflow logic; only release identity differs.

## CI root cause

The Windows desktop runtime test failed at the canonical operator banner fixture:

`expected: E-Stop | CTRL`
`actual:   E-Stop | CTRL & W1P`

Production `_estop_status_text()` intentionally treats W1P as faulted when any of these are unhealthy: local W1P E-stop, internal W1P safety, connection state, validated STATUS freshness, firmware match, or W1P RS485 status. The runtime fixture established only `last_seen` plus a text RS485 state and therefore did not clear all fail-safe W1P conditions left by previous tests.

Changing production logic would have weakened safety and hidden the real test bug. The correct fix is a deterministic fixture: call the existing healthy CTRL/W1P helpers first, then explicitly remove the desired link for each CTRL-only, W1P-only and combined assertion.

## Regression hardening

Added `tools/test_estop_banner_fixture_contract_0609.py` to statically require:

- a fully healthy validated CTRL/W1P baseline before CTRL-only loss;
- explicit CTRL link loss for `E-Stop | CTRL`;
- explicit CTRL restoration before W1P-only loss;
- explicit W1P link loss for `E-Stop | W1P`;
- the canonical combined assertion remains present.

The contract is included in `tools/run_all_source_checks.py`.

## Verification result

`tools/run_all_source_checks.py` reaches `ALL_SOURCE_CHECKS_PASS`.

- EdgeBox integration: 370 checks PASS.
- Historical updater/RS485/safe-update/calibration/motion regressions: PASS.
- `.06.08` regression: PASS.
- `.06.09` E-stop fixture contract: PASS.
- Build pipeline: 53 checks PASS.
- Modbus/wire/speed/motion contracts: PASS.
- Release consistency/source hygiene/Python syntax/SRVR preflight: PASS.
- PySide runtime remains a GitHub CI gate because PySide6 is unavailable locally.
