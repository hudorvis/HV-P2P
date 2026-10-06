# HV P2P v26.10.06.06 deep code audit

## Scope

Locked baseline: `v26.10.06.05`. The reported GitHub failure was audited as a test-harness regression caused by the newly valid `.06.05` yellow motion-zone status states.

## Exact root cause

`SRVR_GitHub_v26.10.06.05/tools/test_backend_logic.py` expected `System | Active` immediately after clearing `_not_calibrated`, but that test section did not reset current position, measured speed, or last signed VEL. Earlier sections had intentionally exercised ramping, limit recall and motion state. Because `.06.05` correctly derives normal-operation status from those values, the fixture could legitimately resolve to a yellow motion-zone status instead of Active.

The production status resolver is correct and remains unchanged.

## Corrective action

The PySide runtime fixture now explicitly creates the state it claims to test: calibrated, healthy, stationary and mid-span. The strict Active assertion is retained unchanged.

A new source-level contract (`test_backend_status_fixture_contract_0606.py`) verifies that the runtime test resets Near/Far/current-position/current-speed/last-signed-VEL before the first Active assertion. This catches the same class of fixture leakage before platform PySide jobs.

## Production lineage audit

After normalising release identity, these production files are unchanged from `.06.05`:

- CTRL EdgeBox firmware;
- W1P EdgeBox firmware;
- CTRL-TS firmware;
- SRVR `backend.py`;
- Run QML;
- Settings QML;
- firmware authority server.

Therefore no operator, motion, RS485, updater or safety behavior was changed for this CI hotfix.

## Verification

The source suite passes all historical regressions, 370 EdgeBox integration checks, the `.06.05` feature regression, the new `.06.06` fixture contract, 53 build-pipeline checks, release consistency, source hygiene, Python syntax and SRVR preflight. PySide runtime/native firmware/frozen desktop builds remain GitHub Actions gates.
