# HV P2P v26.09.15.02 Change Summary

This is the corrective packaging revision following the v26.09.14.03 GitHub native build.

## GitHub failure corrected

The v26.09.14.03 firmware job completed sufficiently for all three SRVR native jobs to start. Both macOS architectures successfully produced and signed an app bundle, and Windows successfully produced an AMD64 executable. All three then failed the frozen-app smoke test with the same message:

`FIRMWARE AUTHORITY STARTUP FAIL: CTRL image missing from immutable bundle`

The staged `SRVR_FIRMWARE_BUNDLE` was valid before deployment. The defect was in Nuitka data-file classification: `.bin` is treated as a binary/executable suffix and is skipped when firmware is carried only by `--include-data-dir`. Therefore `manifest.json` and `SHA256SUMS.txt` were packaged, but `ctrl.bin` and `w1p.bin` were not.

v26.09.15.02 fixes this without weakening firmware validation:

- one shared `tools/patch_pyside_deploy_spec.py` now patches both macOS and Windows deployment specs;
- the ineffective custom `--include-data-dir=firmware_bundle=firmware_bundle` rule is removed;
- `ctrl.bin` and `w1p.bin` are force-included with explicit `--include-data-files=...` rules;
- Windows retains `--assume-yes-for-downloads` and the approved icon setting;
- macOS verifies both firmware images physically exist inside the completed `.app` before signing and smoke testing;
- the macOS release ZIP verifier independently requires all four firmware-bundle files;
- Windows retains the frozen onefile smoke test, which must validate the embedded bundle at runtime;
- a new frozen-firmware-packaging contract test exercises the common spec patcher, including idempotence and legacy-rule removal.

## Build reproducibility hardening

macOS now explicitly pins Nuitka 4.2.1, the exact release observed in the successful v26.09.14.03 macOS deployment stage. Windows remains pinned to Nuitka 4.2 as required by the previously proven Windows CI fixes.

## Regression harness isolation hardening

A repeated/parallel backend stress run found that the test fixture isolated `HOME`, `LOCALAPPDATA` and `APPDATA` but not Linux `XDG_CONFIG_HOME`. On a runner that exports `XDG_CONFIG_HOME`, concurrent tests could therefore share a config file and produce a false joystick-calibration persistence failure. The test now redirects `XDG_CONFIG_HOME` into its per-process temporary home as well. Twenty parallel headless backend regressions pass after the correction. Production config-location behavior is unchanged.

## Clean GitHub-ready source package

The revision ZIP is now intentionally minimal. It excludes superseded change-audit files, old revision summaries/audits, preview/reference screenshots, old wiring-guide copies, generated native outputs and cache files. A new source-package hygiene regression rejects those items if they reappear.

The package retains only the current build source, current workflow/tools, current bootstrap/bench documentation, current change/audit documents, revision history and SHA-256 manifest.

## Preserved behavior

No operator/control behavior was changed for this packaging correction. In particular:

- approved Run and Setup QML remain byte-identical to the locked baseline;
- Speed mode remains W1P DYNAMIC cable-speed PI;
- Power mode remains TRADITIONAL;
- W1P independent 650 ms VEL watchdog remains unchanged;
- stopped/braked OTA gate, Servo Enable inhibition, E-stop/RS485 protections and rollback/recovery remain preserved;
- missing or false `FW_MATCH` remains fail-closed;
- no automatic downgrade is permitted;
- CTRL must match SRVR before CTRL-TS convergence.

Native ESP32 binaries and frozen SRVR applications remain GitHub Actions outputs and are not fabricated in this source ZIP.


## v26.09.15.02 CI hygiene/order correction

- Source-package hygiene remains a strict pristine-source pre-build gate.
- Native firmware output now lives under `RUNNER_TEMP`, outside the repository checkout.
- `native_build_firmware.py` no longer re-runs source-package hygiene after compilation has legitimately created native artifacts.
- The native builder proves CTRL/CTRL-TS/W1P authoritative source trees are byte-for-byte unchanged after compilation.
- Generated Arduino `build/` directories are removed from `STAGED_SOURCE` before artifact preservation to avoid duplicate `.bin` payloads.
- The master source runner sets `PYTHONDONTWRITEBYTECODE=1` and uses `test_python_syntax.py`, so repeated source checks do not create `__pycache__`/`.pyc` contamination.

- Added `test_native_build_orchestration.py` to permanently exercise pre/post build phase separation, staged-source cleanup, immutable bundle creation, and checkout immutability using temporary synthetic fixtures only.
- Repeated master-source runs are now idempotent and leave no `__pycache__` or `.pyc` files.
