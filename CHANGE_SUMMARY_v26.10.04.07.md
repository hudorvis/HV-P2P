# HV P2P v26.10.04.07 change summary

Date: 2026-10-04

Authoritative lineage: `HV P2P v26.10.04.06 - GitHub Ready Source.zip` -> this `.04.07` CI/runtime-regression correction.

## 1. GitHub macOS backend test failure

The `.04.06` production backend intentionally changed Limit Calibration to exactly three captures: `Near -> Far -> Ref & Done`. On the Ref capture the backend stores the reference, exits calibration/service ownership, forces Battery Change Mode Off and closes the wizard while `calibration_step` remains the terminal zero-based step index `2`.

`SRVR_GitHub_v26.10.04.06/tools/test_backend_logic.py` still contained an older four-step expectation (`calibration_step == 3`, followed by a separate `Done` call). GitHub therefore failed even though the backend itself was following the approved three-step design.

`.04.07` updates both Limit Calibration regression sections to assert the actual contract: after the third Ref confirmation, `calibration_step == 2`, calibration is closed and the saved Ref is correct.

## 2. Late/duplicate confirmation hardening

`calibrationNext()` now immediately returns when no calibration wizard is open. This makes a delayed or duplicate CTRL-TS/SRVR confirmation harmless after the third Limit step has already completed. The regression explicitly changes the live position after close, injects another `calibrationNext()`, and verifies the saved Ref cannot be recaptured.

## 3. Scope

No motion control, RS485 timing/scheduling, W1P 500 ms velocity watchdog, Leadshine control, AUX delivery, firmware-update transport, QML layout or limit-calibration geometry is changed by this revision. The change is deliberately limited to the runtime test contract plus the post-close duplicate-confirm guard.

## Verification

The complete source/static/preflight suite is run from the final `.04.07` layout. GitHub Actions remains authoritative for PySide6 runtime execution, native ESP32 builds and frozen desktop builds.
