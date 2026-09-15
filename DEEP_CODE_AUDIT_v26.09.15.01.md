# HV P2P v26.09.15.01 Deep Code Audit

## Evidence from v26.09.14.03 GitHub build

The three reported desktop failures were the same frozen-resource defect:

- macOS Intel: app deployment, architecture check and code signing reached the smoke test, then firmware authority reported missing CTRL image;
- macOS Apple Silicon: same result;
- Windows x64: Nuitka produced a valid AMD64 PE (`0x8664`), then the frozen smoke test reported the same missing CTRL image.

Because both SRVR jobs have `needs: build-firmware`, reaching these native deployment stages also confirms the upstream firmware job completed and supplied `NATIVE_BUILD_FOR_SRVR/SRVR_FIRMWARE_BUNDLE` to the desktop jobs.

## Root cause

The staging tree contained and successfully validated all four immutable bundle files. The deployment spec then relied on:

`--include-data-dir=firmware_bundle=firmware_bundle`

Nuitka intentionally excludes file types it treats as executable/code from ordinary data-directory inclusion; `.bin` is one of those suffixes. The logs are consistent with this: the text manifest/checksum files were discovered, but the two ESP `.bin` images were absent from the frozen runtime.

## Corrections

1. Added one shared spec patcher for macOS and Windows.
2. Removed the ineffective custom firmware `--include-data-dir` rule.
3. Force-included exact `firmware_bundle/ctrl.bin` and `firmware_bundle/w1p.bin` target paths with `--include-data-files`.
4. Retained Windows `--assume-yes-for-downloads` and icon handling in the same common patcher.
5. Added macOS completed-app assertions for both firmware images before signing/smoke testing.
6. Added macOS release-ZIP assertions for `manifest.json`, `SHA256SUMS.txt`, `ctrl.bin` and `w1p.bin`.
7. Retained Windows frozen smoke testing as the authoritative onefile payload check.
8. Added an 18-check frozen-firmware packaging contract including an idempotent representative-spec patch test.
9. Pinned macOS Nuitka 4.2.1; preserved Windows Nuitka 4.2.
10. Added source-package hygiene checks so future GitHub-ready revision ZIPs remain minimal.
11. Stress testing found the Linux backend regression fixture could inherit a shared `XDG_CONFIG_HOME`; the fixture now isolates it per process. Twenty parallel headless backend regressions pass after this test-only correction.

## Regression and safety reconciliation

The v26.09.14.03 backend/safety corrections remain intact:

- missing `FW_MATCH` is fail-closed;
- a W1P HELLO clears stale authority/RS485 state;
- motion/RS485 health requires a fresh complete STATUS;
- malformed STATUS cannot retain stale good state.

Preservation checks still lock:

- Run/Main QML SHA-256 `60edb4348c98827902f21006ffa4e4aa274e65d0527f32782f5f3de97bead93e`;
- Setup QML SHA-256 `9cede2819a4c7d931247121711d2441e01537fdd05c804b0fc646caa5fded7fd`;
- W1P 650 ms VEL watchdog;
- W1P stopped/braked OTA service gate;
- established Speed/Power behavior;
- CTRL/W1P authority-header parity and Arduino `HEX_DIGITS` collision fix.

## Local validation

The complete source suite passes locally, including EdgeBox integration, OTA authority contracts, backend regression, native-build pipeline contracts, frozen-firmware packaging contract, protocol tests, release consistency, source-package hygiene, Python compilation, SRVR preflight and workflow YAML parsing.

The local environment cannot perform the authoritative ESP32/macOS/Windows native builds. GitHub Actions remains the required compile/frozen-runtime gate, followed by physical bench commissioning.
