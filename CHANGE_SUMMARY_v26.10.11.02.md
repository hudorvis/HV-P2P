# HV P2P v26.10.11.02 change summary

Date: 2026-10-11

Source baseline: **v26.10.11.01**. This is a narrowly scoped CI/regression repair. CTRL, W1P and CTRL-TS production behaviour, SRVR UI/QML, motion, limits, calibration, AUX, firmware authority/update ordering, 115200/8N1 EL7 operation, AI0/5 V W1P E-stop and EdgeBox DO0 brake control remain locked.

## GitHub failure reviewed

The supplied GitHub Actions output did **not** reach the frozen macOS application build. `backend` imported successfully, then `python -m tools.test_backend_logic` failed in the config-backup recovery test with:

`FileNotFoundError: .../hvp2p-srvr-smoke-.../config.json`

The failure was introduced by the `.11.01` smoke-persistence isolation change. Every `HVP2PBackend(smoke_test=True)` instance created its own temporary directory. The historical recovery test intentionally creates a second fresh Backend instance to prove that a corrupt primary config is restored from the previous-good `.bak`; because the second instance got a different temporary directory, it could not see the first instance's config/backup.

## Fix

Smoke-test persistence is now **private per process**, rather than private per Backend object:

- the first smoke Backend in a process creates one `hvp2p-srvr-smoke-*` directory;
- later Backend instances in that same smoke process reuse it;
- source/frozen smoke processes remain isolated from each other and from the operator's real `Application Support/HV P2P SRVR` data;
- an `atexit` cleanup removes the private directory at normal process exit;
- individual Backend shutdown no longer deletes the shared smoke directory prematurely.

The backup/recovery regression now explicitly asserts that a fresh Backend in the same smoke process uses the same config path before checking recovery from `.bak`. This directly protects the exact GitHub failure.

## Deep project check

The complete source-level project audit was rerun after the fix. Results include:

- **386 EdgeBox integration checks** passed;
- **58 build-pipeline checks** passed;
- all historical HMI/RS485/updater/OTA/calibration/motion/limit/AUX regressions reached before the combined-runner execution limit passed;
- the remaining Modbus, SRVR wire, Speed Mode, motion-innovation, release-consistency, source-hygiene, Python-syntax and SRVR preflight checks were run individually and passed;
- the full backend regression, including the previously failing config-backup recovery case, passed with a QtCore-compatible test double in this environment;
- production W1P, CTRL and CTRL-TS source is byte-equivalent to `.11.01` after normalising only the release version;
- all SRVR QML files are byte-identical to `.11.01`.

The native ESP32 builds and actual frozen macOS/Windows application runs remain GitHub Actions gates. The updated CI must still prove the pinned macOS frozen runtime after this source-test blocker is cleared.
